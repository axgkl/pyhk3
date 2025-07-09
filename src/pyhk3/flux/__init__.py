import base64
import os
from glob import glob
from os.path import exists

from .. import kubectl
import sh
import yaml

from ..ssh import ensure_forward
from ..tools import require_cmd, confirm, die, log, read_file, run, const, shw, write_file
from ..tools import need_env as E
from ..tools import dir_, cmd, read_yaml, write_yaml, to_yaml
from .git_ import git

req_cmds = cmd('kubectl', 'sops', 'helm', use='--help') + cmd('age', 'git', 'flux')


def reconcile():
    # TODO: fix
    run('flux reconcile source git flux-system')
    run('flux reconcile kustomization flux-system')


def fn_pubkey():
    p = E('GITOPS_ENV')
    return f'age-key-{p}.pub'


def install():
    """To uninstall use: flux uninstall."""
    ensure_forward()
    d = git.pull()
    env = E('GITOPS_ENV')
    host = E('GITOPS_HOST')
    os.environ['GITLAB_TOKEN'] = E('GITOPS_TOKEN')
    if not 'gitlab' in host:
        die('Only gitlab is supported at this time')
    pth = f'clusters/{env}'
    if os.path.exists(f'{d}/{pth}'):
        if os.system('flux check'):
            die(
                'Repo has flux but flux check failed',
                hint='Clean manually. E.g. flux uninstall, then clear repo?',
            )
        return log.info('flux already installed')
    git.push()
    run('flux check --pre')
    sh.flux.bootstrap.gitlab(
        f'--owner={E("GITOPS_OWNER")}',
        f'--path={pth}',
        f'--repository={E("GITOPS_REPO")}',
        f'--hostname={host}',
        f'--branch={env}',
        '--token-auth',
    )
    run('flux check')
    log.info('Flux installed')


def _prepare_repo():
    ensure_forward()
    d = git.pull()
    return d, git.get_adder(d), E('GITOPS_ENV')


def add_validator():
    d, add, env = _prepare_repo()
    s = read_file(dir_(__file__) + '/scripts/validate.sh')
    add('scripts/validate.sh', s, mkdir=True, chmod=0o755)
    git.push('validater')


def add_sops_secret():
    d, write_add, env = _prepare_repo()
    s, k = 'sops-age', 'age.agekey'
    priv = kubectl.ensure_secret(s, k, ns='flux-system', envkey='GITOPS_FLUX_PRIV_SECRET')
    fns = f'{d}/{fn_pubkey()}'
    s = read_file(fns, '')
    pubkey = kubectl.age_pub_from_priv(priv)
    assert pubkey in priv  # sanity check
    if s:
        if s != pubkey:
            die('Public key mismatch', pub=pubkey, fns=fns)
    else:
        write_add(fn_pubkey(), pubkey)
    fns = f'clusters/{env}/flux-system/gotk-sync.yaml'
    fn = f'{d}/{fns}'
    la = list(yaml.safe_load_all(read_file(fn)))
    k = [l for l in la if l['kind'] == 'Kustomization'][0]
    k['spec']['decryption'] = {'provider': 'sops', 'secretRef': {'name': 'sops-age'}}
    write_add(fns, yaml.dump_all(la))
    write_add(f'.sops.{env}.yaml', TSY.replace('<PUBKEY>', pubkey))
    git.push('sops pub key added')
    log.info('Decryption provider added to gotk-sync.yaml')


_here = lambda: dir_(__file__)


def add_infra_and_apps_skeleton():
    return add_app('skeleton', 'SRC/skel')


def add_infra_ingress_nginx():
    return add_app('ingress-nginx', 'SRC/ingress-nginx')


def _encrypt(d, y):
    pubkey = read_file(f'{d}/{fn_pubkey()}').strip()
    fn = f'{d}/tmp.yaml'
    write_file(fn, y)
    sh.sops(
        '--encrypt',
        '--age',
        pubkey,
        '--in-place',
        '--encrypted-regex',
        '^(data|access-token)$',
        fn,
    )
    s = read_file(fn)
    os.unlink(fn)
    return s


def add_infra_certmgr():
    return add_app('certmgr', 'SRC/cert-manager')


nil = '\x01'

procs = {'b64': lambda s: base64.b64encode(s.encode('utf-8')).decode('utf-8')}


class IG:
    def __init__(self, ctx):
        self.d = ctx

    def __getitem__(self, k, v=nil):
        l = k.split(':')
        k = l.pop(0)
        posts = [procs[i] for i in l]
        if k.startswith('$'):
            v = E(k[1:])
        if v == nil:
            breakpoint()  # FIXME BREAKPOINT
        for p in posts:
            v = p(v)
        return v


_repl = lambda s: s if not '%(' in s else s % IG({})
_is_secr_kind = lambda i: i.rstrip().lower().replace(' ', '') == 'kind:secret'


def add_app(name, dir, l=None):
    dflx, add, env = l or _prepare_repo()
    env = E('GITOPS_ENV')
    dir = dir.replace('SRC', _here() + '/yamls')
    for D, _, fns in os.walk(dir):
        for fn in fns:
            fpth = os.path.join(D, fn)
            pth = fpth[len(dir) + 1 :]
            pth = pth.replace('/_env_/', f'/{env}/')
            y = _repl(read_file(fpth))
            if fn == 'kustomization.yaml':
                y = _merge_kust(y, dflx + '/' + pth)
            if any([i for i in y.splitlines() if _is_secr_kind(i)]):
                y = _encrypt(dflx, y)
            add(pth, y)
    git.push(f'Added {name}')


def _merge_kust(y, pth):
    n = read_yaml(y)
    o = read_yaml(pth) if exists(pth) else {'resources': []}
    r = o['resources']
    o.update(n)
    [o['resources'].insert(0, i) for i in r if not i in o['resources']]
    return to_yaml(o)


TK = """
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: []
"""


TSY = """
creation_rules:
  - path_regex: \.yaml$
    encrypted_regex: ^(data|stringData)$
    age: <PUBKEY>
"""


def info():
    run('flux get all --all-namespaces')


def uninstall():
    """this is just a temporary helper for repeasted tries of the exmple flux tmpl install"""
    d, add, env = _prepare_repo()
    ensure_forward()
    l = ['cert-manager', 'ingress-nginx', 'podinfo']
    confirm(f'Uninstall flux, cleaning repo, removing {l}?', default=False)
    run('flux uninstall', no_fail=const.silent)
    for h in l:
        run(f'helm uninstall {h}', no_fail=const.silent)
        run(f'kubectl delete namespace {h}', no_fail=const.silent)
    log.info('Emptying repo')
    l = ['clusters', 'infrastructure', 'apps', 'scripts']
    [sh.rm('-rf', f'{d}/{k}') for k in l]
    [sh.rm('-f', k) for k in glob(f'{d}/age-key-*')]
    git.push('removed all')
    log.info('empty repo pushed')


class flux:
    ensure_requirements = lambda: require_cmd(*req_cmds)
    install = install
    add_validator = add_validator
    add_sops_secret = add_sops_secret
    add_infra_and_apps_skeleton = add_infra_and_apps_skeleton
    add_infra_ingress_nginx = add_infra_ingress_nginx
    add_infra_certmgr = add_infra_certmgr
    add_app = add_app
    uninstall = uninstall
    info = info
    reconcile = reconcile
