import structlog
import os
import sys
import sh
import json
import subprocess
import importlib.util

from rich.console import Console
from rich.prompt import Confirm
from .cache import nil
from .defaults import envdefaults
import time

import yaml

console = Console()
now = lambda: int(time.time() * 1000)
T0 = now()


exists = os.path.exists


class const:
    silent = 'silent'


def read_yaml(fn):
    return yaml.safe_load(read_file(fn))


def to_yaml(struct):
    dump = yaml.dump
    if isinstance(struct, list):
        dump = yaml.dump_all
    return dump(struct, default_flow_style=False)


def write_yaml(fn, struct):
    write_file(fn, to_yaml(struct), mkdir=True)


def tar_pipe(d_src, d_tgt):
    src_pipe = sh.tar.cf('-', '.', _cwd=d_src, _piped=True)
    sh.tar.xf('-', '-C', d_tgt, _in=src_pipe)
    log.info('copied', src=d_src, into=d_tgt)


def do_git(f, *a, d=None, **kw):
    kw['_cwd'] = d
    if d:
        kw['_cwd'] = d.replace(os.getcwd(), '.')
    log.info(f'git {f} {" ".join(list(a))}', **kw)
    kw['_cwd'] = d
    return getattr(sh.git, f)(*a, **kw)


def cmd(*cmd, use='--version'):
    return [f'{c} {use}' for c in cmd]


def require_cmd(*cmd):
    l = [f'{c} 2>/dev/null 1>/dev/null' for c in cmd]
    c = ' && '.join(l)
    if os.system(c) == 0:
        return
    if os.system(l[0]):
        die(f'Missing required command: {cmd[0]}')
    [require_cmd(c) for c in cmd]


def confirm(msg, default=False):
    r = Confirm.ask(msg, default=default)
    if not r:
        die('Aborted by user')


_secrets = {}

called = []


def shw(f, *a, **kw):
    origf = getattr(f, 'func', f)
    n = origf.__name__
    if not 'lambda' in n:
        called.append(n)
        log.info(f'⏺️ {n}')
    return f(*a, **kw)


class TemplRepl:
    add = {}

    def __getitem__(self, k, dflt=None):
        k, dflt = (k + '|').split('|')[:2]
        r = env(k, self.add.get(k, nil))
        if r == nil:
            if dflt is not None:
                return dflt
            die(f'Missing env var ${k}')
        return r


env_templ_repl = TemplRepl()


def render_env_into(tmpl, add=None):
    if add:
        env_templ_repl.add.update(add)
    tmpl = tmpl.replace('T(', '%(')
    tmpl = tmpl % env_templ_repl
    tmpl = tmpl.replace('True', 'true').replace('False', 'false')
    return tmpl + '\n'


def dir_(filename):
    return os.path.dirname(os.path.abspath(filename))


def import_file(filename):
    d = dir_(filename)
    sys.path.append(d) if d not in sys.path else None
    return importlib.import_module(filename)


def pyval(k, fn, dflt=None):
    if not os.path.exists(f'{fn}.py'):
        die('Missing pyval file', k=k, fn=fn)
    mod = import_file(fn)
    v = getattr(mod, k, nil)
    if v == nil:
        if dflt is not None:
            return dflt
        die('Missing pyval var', k=k, fn=fn)
    return v


env_key_on_missing = '__env_key_on_missing__'


def env(key, dflt=None):
    v = os.environ.get(key, nil)
    if v == nil:
        v = getattr(envdefaults, key, dflt)
    if str(v).startswith('py:'):
        v = pyval(key, v[3:], dflt)
    # not elif, pyval may return pass:...
    if str(v).startswith('pass:'):
        x = _secrets.get(v, nil)
        if x == nil:
            try:
                x = pass_(v[5:], for_=key)  # .show(v[5:], _fg=True).strip()
            except Exception as ex:
                # special case: allows to calc and  set the value later:
                if dflt == env_key_on_missing:
                    return v
                if dflt is None:
                    die('Running pass utility', key=v[5:], exc=ex)
                return dflt
            _secrets[v] = x
        v = x
    return v


def need_env(k, dflt=None, _home_repl=False):
    v = env(k, dflt)
    if v is None:
        die(f'Missing env var ${k}')
    if _home_repl:
        for k in '~', '$HOME':
            v = v.replace(k, os.environ['HOME'])
    return v


def add_to_pass(key, val):
    log.warn('Adding key to pass', n=key[5:])
    getattr(sh, 'pass', None).insert('-m', key[5:], _in=val)
    if not pass_(key, for_='age').show(key[5:], _err=[1, 2]).strip() == val:
        die('Failed to update pass', key=key[5:], value=val)


def pass_(key, for_):
    try:
        result = subprocess.run(
            ['pass', 'show', key],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except KeyboardInterrupt as _:
        die('Interrupted - bye')
    return result.stdout.strip()


# p = getattr(sh, 'pass', None)
# h = 'Install pass: https://www.passwordstore.org/'
# h += '- or supply a wrapper, supporting show and insert [-m] methods, e.g. for reading/writing files'
# if p is None:
#     die('pass utility not found', hint=h, required_for=key)
# return p


def dt(_, __, e):
    e['timestamp'] = f'{now() - T0:>4}'
    return e


structlog.configure(
    processors=[
        # structlog.processors.TimeStamper(fmt='iso'),
        dt,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)

log = structlog.get_logger()


def die(msg, no_fail=False, **kw):
    log.fatal(msg, **kw)
    if no_fail:
        if no_fail == const.silent:
            return log.info('Ignoring failure')
        raise Exception(msg)
    sys.exit(1)


def run(cmd, bg=False, no_fail=False, **kw):
    i = kw.get('input')
    if i is not None and not kw.get('text', False):
        kw['input'] = i.encode() if isinstance(i, str) else i
    if isinstance(cmd, str):
        cmd = cmd.split()
    pipe = kw.get('pipe', '')
    pipe = pipe if not len(pipe) > 20 else f'{pipe[:20]}...'
    lw = {}
    if pipe:
        lw['pipe'] = pipe
    log.debug(f'⚙️ {" ".join(cmd)}', **lw)
    if bg:
        r = subprocess.Popen(cmd, start_new_session=True)
        # r.communicate()
        return r

    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        die('Command failed', cmd=cmd, returncode=r.returncode, no_fail=no_fail)
    return r.stdout.strip() if r.stdout else ''


def ssh(ip, port=None, cmd=None, input=None, send_env=None, capture_output=True, **kw):
    cmd = cmd if cmd is not None else 'bash -s'
    port = port if port is not None else int(env('SSH_PORT', 22))
    c = f'ssh -p {port} -o StrictHostKeyChecking=accept-new -i'.split()
    cmd = c + [need_env('FN_SSH_KEY', _home_repl=True), f'root@{ip}', cmd]
    kw['capture_output'] = capture_output
    for key in send_env or []:
        cmd.insert(1, f'SendEnv={key}')
        cmd.insert(1, '-o')
    if cmd[-1] == 'args':  # for os.system style
        return [f'{e}' for e in cmd[1:-1]]
    kw['text'] = kw.get('text', True)
    return run(cmd, input=input, **kw)


def write_file(fn, s, log=0, mkdir=0, chmod=None, mode='w'):
    "API: Write a file. chmod e.g. 0o755 (as octal integer)"

    fn = os.path.abspath(fn)

    if log > 0:
        log.info('Writing file', fn=fn)

    if isinstance(s, (list, tuple)) and s and isinstance(s[0], str):
        s = '\n'.join(s)

    elif isinstance(s, (dict, tuple, list)):  # think of bytes, mode wb
        s = json.dumps(s, default=str)
    e = None
    for _ in 1, 2:
        try:
            with open(fn, mode) as fd:
                fd.write(s)
            if chmod:
                if not isinstance(chmod, (list, tuple)):
                    chmod = [int(chmod)]
                for s in chmod:
                    os.chmod(fn, s)
            return fn
        except IOError as ex:
            if mkdir:
                d = os.path.dirname(fn)
                os.makedirs(d, exist_ok=True)
                continue
            e = ex
        except Exception as ex:
            e = ex
        raise Exception('Could not write file: %s %s' % (fn, e))


def read_file(fn, dflt=None, mkfile=False, bytes=-1, strip_comments=False):
    """
    API function.
    read a file - return a default if it does not exist"""
    if not exists(fn):
        if dflt is not None:
            if mkfile:
                write_file(fn, dflt, mkdir=1)
            return dflt
        if mkfile:
            raise Exception(fn, 'Require dflt to make non existing file')
        raise Exception(fn, 'does not exist')
    with open(fn) as fd:
        # no idea why but __etc__hostname always contains a linesep at end
        # not present in source => rstrip(), hope this does not break templs
        res = fd.read(bytes)
        res = res if not res.endswith('\n') else res[:-1]
        if strip_comments:
            lines = res.splitlines()
            res = '\n'.join([l for l in lines if not l.startswith('#')])
        return res


env('DOMAIN')
env('DOMAIN')
