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


# class tools:
#     read_yaml = read_yaml
#     write_yaml = write_yaml
#
# def git_clone_after_rm(url, into):
#     """Clone a git repo and remove files after"""
#     env = E('GITOPS_ENV')
#     sh.rm('-rf', into)
#     sh.git.clone(url, into)
#     with sh.pushd(into):
#         try:
#             sh.git.checkout(env)
#         except Exception as _:
#             sh.git.checkout('-b', env)
#             sh.touch('README.md')
#             sh.git.commit('-am', 'branch creeated', _ok_code=[0, 1])
#             sh.git.push('-u', 'origin', env)
#             log.info('Pushed new branch', name=env)
#     log.info('Cloned', url=url, into=into, branch=env)
#     return into

# def get_clean_repo(url=None, d=None):
#     sh.mkdir('-p', os.path.dirname(d_our_repo))
#     if not url:
#         url = f'git@{E("GITOPS_HOST")}:{E("GITOPS_OWNER")}/{E("GITOPS_REPO")}'
#         d = d_our_repo
#     return tools.git_clone_after_rm(url, d)

# def do(f, d, *a):
#     shw(f, d, *a)
#     git(d, add='.', msg=f'{f.__name__} (flux setup)')


# def git(d, add='', msg=None, push=False):
#     with sh.pushd(d):
#         if add:
#             sh.git.add(add)
#         if msg:
#             sh.git.commit('-am', msg, _ok_code=[0, 1])
#         if push:
#             sh.git.push()
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


def _empty_kust(dir_, add, fn='kustomization.yaml'):
    TK = """
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: []
"""
    return add(f'{dir_}/{fn}', TK, mkdir=True)


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


def add_infra_and_apps_skeleton():
    d, add, env = _prepare_repo()
    for D in 'apps', 'infrastructure':
        s = read_file(dir_(__file__) + f'/yamls/clusters/{D}.yaml')
        s = s.replace('_ENV_', env)
        add(f'clusters/{env}/{D}.yaml', s, mkdir=True)
    _empty_kust(f'infrastructure/{env}/controllers', add)
    _empty_kust(f'infrastructure/{env}/configs', add)
    _empty_kust(f'apps/{env}', add)
    git.do('commit', '-am', 'Added skeleton for infra and apps', d=d, _ok_code=[0, 1])


def add_yml(pth, fn, l, cb=None, yml=None):
    d, add, env = l
    fn += '.yaml'
    y = yml
    if yml is None:
        y = read_file(dir_(__file__) + f'/yamls/{pth}/{fn}')
    y = cb(y) if cb else y
    pth = pth.replace('infrastructure/', f'infrastructure/{env}/')
    pth = pth.replace('apps/', f'apps/{env}/')
    pthf = d + '/' + pth
    s = read_yaml(pthf + '/kustomization.yaml')
    s['resources'].append(fn) if not fn in s['resources'] else 0
    write_yaml(pthf + '/kustomization.yaml', s)
    add(pth + '/' + fn, y)


def add_infra_ingress_nginx():
    l = _prepare_repo()
    add_yml('infrastructure/controllers', 'ingress-nginx', l)
    git.push('Added ingress-nginx')


T_DNS_SECRET = """
apiVersion: v1
kind: Secret
metadata:
    name: %(provider)s-dns-token
    namespace: cert-manager
data:
    access-token: %(token)s
"""


def add_infra_dns_secret(l=None):
    l = l or _prepare_repo()
    provider = E('DNS_PROVIDER')
    token = E('DNS_API_TOKEN')
    token = base64.b64encode(token.encode('utf-8')).decode('utf-8')
    y = T_DNS_SECRET % {'provider': provider, 'token': token}
    y = _encrypt(l[0], y)
    add_yml('infrastructure/controllers', 'dns-secret', l, yml=y)


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
    l = _prepare_repo()
    breakpoint()  # FIXME BREAKPOINT
    add_yml('infrastructure/controllers', 'cert-manager', l)
    add_infra_dns_secret(l)

    def r(s):
        s = yaml.safe_load(s)
        t = {'key': 'access-token', 'name': 'digitalocean-dns-token'}
        t = {'digitalocean': {'tokenSecretRef': t}}
        s['spec']['acme']['solvers'][0]['dns01'] = t
        s['spec']['acme']['email'] = E('EMAIL')
        s['spec']['acme']['server'] = 'https://acme-v02.api.letsencrypt.org/directory'
        return to_yaml(s)

    add_yml('infrastructure/configs', 'cluster-issuers', l, r)
    git.push('Added cert-manager')


TSY = """
creation_rules:
  - path_regex: \.yaml$
    encrypted_regex: ^(data|stringData)$
    age: <PUBKEY>
"""


def add_tmpl(tmpl_url):
    """Prepare the repository for flux

    Basically we push flux example into our gitlab repo, so that flux instal finds sth
    into_repo: e.g.: 'gh:/fluxcd/flux2-kustomize-helm-example'
    """
    d_our_repo = tools.get_clean_repo()

    # return add_dns_secret(d_repo, pubkey)

    if tmpl_url.startswith('gh:'):
        tmpl_url = f'https://github.com{tmpl_url[3:]}'
    os.makedirs('./tmp', exist_ok=True)
    d_tmpl = './tmp/tmpl.git'
    rm = ['README.md', 'LICENSE', 'CODE_OF_CONDUCT.md', 'CONTRIBUTING.md', '.git']
    tools.git_clone_after_rm(tmpl_url, d_tmpl, rm_after=rm)
    tools.tar_pipe(d_tmpl, d_our_repo)
    with sh.pushd(d_our_repo):
        for k in 'gotk-components.yaml', 'gotk-sync.yaml':
            k = f'{E("GITOPS_PATH")}/flux-system/{k}'
            log.info('Restoring', fn=k)
            sh.git.checkout(k)
    git(d_our_repo, add='.', msg=f'templ overlay\n\n{tmpl_url}\n->\n{d_our_repo}')
    push_and_reconcile(d_our_repo)  # secret reqs certmanager, one go did not work
    adapt_template(d_our_repo, tmpl_url.split('/')[-1])


def adapt_template(d_our_repo, tmpl):
    """Add decryption provider to flux-system"""
    modifier_func = tmpl_modifiers.get(tmpl, lambda d: d)
    modifier_func(d_our_repo)
    push_and_reconcile(d_our_repo)


def push_and_reconcile(d_our_repo):
    q = 'Can I push it? Please, check the repo commits first:'
    confirm(f'{q} {d_our_repo}', default=True)
    git(d_our_repo, push=True)
    shw(reconcile)


def flux_kust_helm_exmpl(d):
    def add_dns_secret(d):
        pth = E('GITOPS_PATH')
        pubkey = read_file(f'{d}/{tools.fn_pubkey()}').strip()
        provider = E('DNS_PROVIDER')
        token = E('DNS_API_TOKEN')
        token = base64.b64encode(token.encode('utf-8')).decode('utf-8')
        y = T_DNS_SECRET % {'provider': provider, 'token': token}
        dc = f'{d}/{pth}'
        fn = f'{dc}/dns-secret.yaml'
        fk = f'{dc}/kustomization.yaml'
        write_file(fn, y)
        # write_file(fk, K)
        sh.sops(
            '--encrypt',
            '--age',
            pubkey,
            '--in-place',
            '--encrypted-regex',
            '^(data|access-token)$',
            fn,
        )

    def set_dns01_solver(d):
        fn = f'{d}/infrastructure/configs/cluster-issuers.yaml'
        prvdr = E('DNS_PROVIDER')
        y = yaml.safe_load(read_file(fn))
        s = y['spec']['acme']['email'] = E('EMAIL')
        s = y['spec']['acme']['solvers']
        s.clear()
        t = {'name': f'{prvdr}-dns-token', 'key': 'access-token'}
        dns = {prvdr: {'tokenSecretRef': t}}
        s.append({'dns01': dns})
        write_file(fn, yaml.dump(y))

    def enable_dns(d):
        D = E('DOMAIN')
        k = 'production'
        fn = f'{d}/apps/{k}/podinfo-values.yaml'
        l = list(yaml.safe_load_all(read_file(fn)))
        l[0]['spec']['values']['ingress']['hosts'][0]['host'] = f'podinfo-{k}.{D}'
        write_file(fn, yaml.dump_all(l))

    def enable_nginx_proxyproto_node_ports(d):
        fn = f'{d}/infrastructure/controllers/ingress-nginx.yaml'
        l = list(yaml.safe_load_all(read_file(fn)))
        for d in l:
            if (
                d.get('kind') == 'HelmRelease'
                and d['metadata']['name'] == 'ingress-nginx'
            ):
                ctrl = d['spec']['values']['controller']
                m = {'use-forwarded-headers': True, 'use-proxy-protocol': True}
                ctrl.setdefault('config', {}).update(m)
                ctrl['service']['nodePorts'] = {'http': 30080, 'https': 30443}
        write_file(fn, yaml.dump_all(l))

    def annotate_podinfo(d):
        fn = f'{d}/apps/production/podinfo-values.yaml'
        l = list(yaml.safe_load_all(read_file(fn)))
        ingress = l[0]['spec']['values']['ingress']
        ingress['annotations'] = {
            'cert-manager.io/cluster-issuer': 'letsencrypt',
            'kubernetes.io/tls-acme': 'true',
        }
        ingress['tls'] = [
            {'secretName': 'podinfo-tls', 'hosts': ['podinfo-production.axiros.axlc.net']}
        ]
        write_file(fn, yaml.dump_all(l))

    do(add_dns_secret, d)
    do(set_dns01_solver, d)
    do(enable_dns, d)
    do(enable_nginx_proxyproto_node_ports, d)
    do(annotate_podinfo, d)


tmpl_modifiers = {'flux2-kustomize-helm-example': flux_kust_helm_exmpl}


def info():
    run('flux get all --all-namespaces')


# def uninstall():
#     """this is just a temporary helper for repeasted tries of the exmple flux tmpl install"""
#     # d = git.pull()
#     ensure_forward()
#     l = ['cert-manager', 'ingress-nginx', 'podinfo']
#     confirm(f'Uninstall flux, cleaning repo, removing {l}?', default=False)
#     run('flux uninstall', no_fail=const.silent)
#     for h in l:
#         run(f'helm uninstall {h}', no_fail=const.silent)
#         run(f'kubectl delete namespace {h}', no_fail=const.silent)
#     log.info('Emptying repo')
#     d_our_repo = tools.get_clean_repo()
#     l = ['clusters', 'infrastructure', 'apps', 'scripts']
#     [sh.rm('-rf', f'{d_our_repo}/{k}') for k in l]
#     [sh.rm('-f', k) for k in glob(f'{d_our_repo}/age-key-*')]
#     git(d_our_repo, add='.', msg='removed all', push=True)
#     log.info('empty repo pushed', repo=d_our_repo)


class flux:
    ensure_requirements = lambda: require_cmd(*req_cmds)
    install = install
    add_validator = add_validator
    add_sops_secret = add_sops_secret
    add_infra_and_apps_skeleton = add_infra_and_apps_skeleton
    add_infra_ingress_nginx = add_infra_ingress_nginx
    add_infra_certmgr = add_infra_certmgr
    add_tmpl = add_tmpl
    adapt_template = adapt_template
    # uninstall = uninstall
    info = info
    reconcile = reconcile
