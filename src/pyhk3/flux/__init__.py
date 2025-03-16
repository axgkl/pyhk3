import base64
import os
from glob import glob

from .. import kubectl
import sh
import yaml

from ..ssh import ensure_forward
from ..tools import confirm, die, log, read_file, run, const, shw, write_file
from ..tools import need_env as E


class tools:
    def fn_pubkey():
        p = E('GITOPS_PATH').rsplit('/', 1)[-1]
        return f'age-key-{p}.pub'

    def tar_pipe(d_src, d_tgt):
        src_pipe = sh.tar.cf('-', '.', _cwd=d_src, _piped=True)
        sh.tar.xf('-', '-C', d_tgt, _in=src_pipe)
        log.info('copied', src=d_src, into=d_tgt)

    def git_clone_after_rm(url, into, rm_after=None):
        sh.rm('-rf', into)
        sh.git.clone(url, into)
        for r in rm_after or []:
            sh.rm('-rf', f'{into}/{r}')
        log.info('Cloned', url=url, into=into, rm=rm_after)
        return into

    def get_repo(url=None, d=None):
        sh.mkdir('-p', './tmp')
        if not url:
            url = f'git@{E("GITOPS_HOST")}:{E("GITOPS_OWNER")}/{E("GITOPS_REPO")}'
            d = './tmp/our-repo.git'
        return tools.git_clone_after_rm(url, d)


def install():
    """To uninstall use: flux uninstall."""
    ensure_forward()
    host = E('GITOPS_HOST')
    os.environ['GITLAB_TOKEN'] = E('GITOPS_TOKEN')
    if not 'gitlab' in host:
        die('Only gitlab is supported at this time')
    run('flux check --pre')
    sh.flux.bootstrap.gitlab(
        f'--owner={E("GITOPS_OWNER")}',
        f'--path={E("GITOPS_PATH")}',
        f'--repository={E("GITOPS_REPO")}',
        f'--hostname={host}',
        f'--branch={E("GITOPS_BRANCH")}',
        '--token-auth',
    )
    run('flux check')
    log.info('Flux installed')


def add_sops_secret():
    ensure_forward()
    d_our_repo = tools.get_repo()
    s, k = 'sops-age', 'age.agekey'
    priv = kubectl.ensure_secret(s, k, ns='flux-system', envkey='GITOPS_FLUX_PRIV_SECRET')

    fns = f'{d_our_repo}/{tools.fn_pubkey()}'
    s = read_file(fns, '')
    pubkey = kubectl.age_pub_from_priv(priv)
    assert pubkey in priv  # sanity check
    if s:
        if s != pubkey:
            die('Public key mismatch', pub=pubkey, fns=fns)
    else:
        write_file(fns, pubkey)
    log.info('Public key written', fns=fns)

    fns = f'{E("GITOPS_PATH")}/flux-system/gotk-sync.yaml'
    fn = f'{d_our_repo}/{fns}'
    la = list(yaml.safe_load_all(read_file(fn)))
    k = [l for l in la if l['kind'] == 'Kustomization'][0]
    k['spec']['decryption'] = {'provider': 'sops', 'secretRef': {'name': 'sops-age'}}
    write_file(fn, yaml.dump_all(la))
    git(d_our_repo, add=tools.fn_pubkey())
    git(d_our_repo, add=fns, msg='sops pub key added', push=True)
    log.info('Decryption provider added to gotk-sync.yaml')


def add_tmpl(tmpl_url):
    """Prepare the repository for flux

    Basically we push flux example into our gitlab repo, so that flux instal finds sth
    into_repo: e.g.: 'gh:/fluxcd/flux2-kustomize-helm-example'
    """
    d_our_repo = tools.get_repo()

    # return add_dns_secret(d_repo, pubkey)
    if tmpl_url.startswith('gh:'):
        tmpl_url = f'https://github.com{tmpl_url[3:]}'
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
    adapt_template(d_our_repo, tmpl_url.split('/')[-1])


def adapt_template(d_our_repo, tmpl):
    """Add decryption provider to flux-system"""
    modifier_func = tmpl_modifiers.get(tmpl, lambda d: d)
    modifier_func(d_our_repo)
    confirm(f'Check repo diff before pushing {d_our_repo}', default=True)
    git(d_our_repo, push=True)


def flux_kust_helm_exmpl(d):
    def add_dns_secret(d):
        pth = E('GITOPS_PATH')
        pubkey = read_file(f'{d}/{tools.fn_pubkey()}').strip()
        provider = E('DNS_PROVIDER')
        token = E('DNS_API_TOKEN')
        token = base64.b64encode(token.encode('utf-8')).decode('utf-8')
        y = T % {'provider': provider, 'token': token}
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
        for k in 'production', 'staging':
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

    do(add_dns_secret, d)
    do(set_dns01_solver, d)
    do(enable_dns, d)
    do(enable_nginx_proxyproto_node_ports, d)


def do(f, d, *a):
    shw(f, d, *a)
    git(d, add='.', msg=f'{f.__name__} (flux setup)')


def git(d, add='', msg=None, push=False):
    with sh.pushd(d):
        if add:
            sh.git.add(add)
        if msg:
            sh.git.commit('-am', msg, _ok_code=[0, 1])
        if push:
            sh.git.push()


tmpl_modifiers = {'flux2-kustomize-helm-example': flux_kust_helm_exmpl}


def info():
    run('flux get all --all-namespaces')


def reconcile():
    # TODO: fix
    run('flux reconcile source git flux-system')
    run('flux reconcile kustomization flux-system')


def uninstall():
    """this is just a temporary helper for repeasted tries of the exmple flux tmpl install"""
    l = ['cert-manager', 'ingress-nginx', 'podinfo']
    confirm(f'Uninstall flux, cleaning repo, removing {l}?', default=False)
    run('flux uninstall', no_fail=const.silent)
    for h in l:
        run(f'helm uninstall {h}', no_fail=const.silent)
        run(f'kubectl delete namespace {h}', no_fail=const.silent)
    log.info('Emptying repo')
    d_our_repo = tools.get_repo()
    l = ['clusters', 'infrastructure', 'apps', 'scripts']
    [sh.rm('-rf', f'{d_our_repo}/{k}') for k in l]
    [sh.rm('-f', k) for k in glob(f'{d_our_repo}/age-key-*')]
    git(d_our_repo, add='.', msg='removed all', push=True)
    log.info('empty repo pushed', repo=d_our_repo)


T = """
apiVersion: v1
kind: Secret
metadata:
    name: %(provider)s-dns-token
    namespace: default
data:
    access-token: %(token)s
"""

TD = """
  decryption:
    provider: sops
    secretRef:
      name: sops-age
"""

K = """
apiVersion: kustomize.toolkit.fluxcd.io/v1beta2
kind: Kustomization
metadata:
  name: test
  namespace: flux-system
spec:
  interval: 10m0s
  path: ./clusters/production
  prune: true
  sourceRef:
    kind: GitRepository
    name: flux-system
  # Decryption configuration starts here
  decryption:
    provider: sops
    secretRef:
      name: sops-age
"""


# def rsync_overlay(d_src, d_tgt):
#     sh.rsync('-a', '--ignore-existing', f'{d_src}/', d_tgt)
#     log.info('copied', src=d_src, into=d_tgt)
# def restore_flux(d):
#     for k in 'production', 'staging':
#         for f in 'gotk-components.yaml', 'gotk-sync.yaml':
#             fnp = f'clusters/{k}/flux-system/{f}'
#             if not fnp.startswith(E('GITOPS_PATH')):
#                 continue
#             fn = f'{d}/{fnp}'
#             if not os.path.exists(fn):
#                 continue
#             os.remove(fn)
#             with sh.pushd(d):
#                 sh.git.checkout(fnp)
#


class flux:
    install = install
    add_sops_secret = add_sops_secret
    add_tmpl = add_tmpl
    adapt_template = adapt_template
    uninstall = uninstall
    info = info
    reconcile = reconcile
