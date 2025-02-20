import structlog
import os
import sys
import json
import subprocess
import importlib.util

from rich.console import Console
from rich.prompt import Confirm
from .cache import nil
from .defaults import envdefaults
import time


console = Console()
now = lambda: int(time.time() * 1000)
T0 = now()


exists = os.path.exists


confirm = Confirm.ask

_secrets = {}

called = []


def shw(f, *a):
    origf = getattr(f, 'func', f)
    n = origf.__name__
    called.append(n)
    return log.info(f'⏺️ {n}') or f(*a)


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


def import_file(filename):
    d = os.path.dirname(os.path.abspath(filename))
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


def env(key, dflt=None):
    v = os.environ.get(key, nil)
    if v == nil:
        v = getattr(envdefaults, key, dflt)
    if str(v).startswith('py:'):
        v = pyval(key, v[3:], dflt)
    elif str(v).startswith('pass:'):
        x = _secrets.get(v, nil)
        if x == nil:
            x = run(['pass', 'show', v[5:]], capture_output=True, text=True) or dflt
            _secrets[v] = x
        v = x
    return v


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


def die(msg, **kw):
    log.fatal(msg, **kw)
    sys.exit(1)


def run(cmd, bg=False, **kw):
    if isinstance(cmd, str):
        cmd = cmd.split()
    pipe = kw.get('pipe', '')
    pipe = pipe if not len(pipe) > 20 else f'{pipe[:20]}...'
    log.debug('⚙️ Cmd', cmd=cmd, pipe=pipe)
    if bg:
        r = subprocess.Popen(cmd, start_new_session=True)
        # r.communicate()
        return r

    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        die('Command failed', cmd=cmd, returncode=r.returncode)
    return r.stdout.strip() if r.stdout else ''


def need_env(k, dflt=None):
    v = env(k, dflt)
    if v is None:
        die(f'Missing env var ${k}')
    return v


def ssh(ip, port=None, cmd=None, input=None, send_env=None, capture_output=True, **kw):
    cmd = cmd if cmd is not None else 'bash -s'
    port = port if port is not None else int(env('SSH_PORT', 22))
    c = f'ssh -p {port} -o StrictHostKeyChecking=accept-new -i'.split()
    cmd = c + [need_env('FN_SSH_KEY'), f'root@{ip}', cmd]
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
                os.makedirs(d)
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
