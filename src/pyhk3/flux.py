from .ssh import ensure_forward
from .tools import run, log, die, need_env as E, read_file, env_key_on_missing
from .tools import add_to_pass
from .kubectl import ensure_namespace
import os
import sh
# from kubernetes import client, config
# # Load the kubeconfig file
# config.load_kube_config()
# # Create a V1Namespace object
# namespace = client.V1Namespace(metadata=client.V1ObjectMeta(name='my-namespace'))
# # Create the namespace using the CoreV1Api
# v1 = client.CoreV1Api()
# breakpoint()  # FIXME BREAKPOINT
# v1.create_namespace(namespace)


def install():
    """To uninstall use: flux uninstall."""
    host = E('GITOPS_HOST')
    os.environ['GITLAB_TOKEN'] = E('GITOPS_TOKEN')
    if not 'gitlab' in host:
        die('Only gitlab is supported at this time')
    ensure_forward()
    run('flux check --pre')
    ensure_namespace('flux-system')
    ns = ('--namespace', 'flux-system')
    have = sh.kubectl.get('secrets', *ns)
    if 'sops-age' in have:
        die('Secret already exists', hint='run: flux check, possibly then flux uninstall')
    S = 'AGE-SECRET-KEY'
    s = priv = E('GITOPS_FLUX_PRIV_SECRET', env_key_on_missing)
    if S in s:
        log.info('Using existing secret')
    else:
        log.warn('No GITOPS_FLUX_PRIV_SECRET - gen.ing new one using age')
        priv = sh.age_keygen().strip().split('\n')[-1]
        assert priv.startswith(S)

    _ = '--from-file=age.agekey=/dev/stdin'
    sh.kubectl.create.secret.generic('sops-age', _, *ns, _in=priv)
    cmd = [
        'flux',
        'bootstrap',
        'gitlab',
        f'--owner={E("GITOPS_OWNER")}',
        f'--path={E("GITOPS_PATH")}',
        f'--repository={E("GITOPS_REPO")}',
        f'--hostname={host}',
        f'--branch={E("GITOPS_BRANCH")}',
        '--token-auth',
    ]
    run(cmd)
    if s.startswith('pass:'):
        add_to_pass(s, priv)


def clone(url, into):
    sh.rm('-rf', into)
    sh.git.clone(url, into)
    log.info('Cloned', url=url, into=into)


def prepare_repo(tmpl_url, into_repo=None):
    """Prepare the repository for flux."""
    sh.mkdir('-p', './tmp')
    if not into_repo:
        into_repo = f'git@{E("GITOPS_HOST")}:{E("GITOPS_OWNER")}/{E("GITOPS_REPO")}'
    di = './tmp/into.git'
    clone(into_repo, di)

    if tmpl_url.startswith('gh:'):
        tmpl_url = f'https://github.com{tmpl_url[3:]}'
    d_src = './tmp/tmpl.git'
    clone(tmpl_url, d_src)

    for r in ['README.md', 'LICENSE', 'CODE_OF_CONDUCT.md', 'CONTRIBUTING.md', '.git']:
        sh.rm('-rf', d_src + '/' + r)

    tar_command = sh.tar('cf', '-', '.', _cwd=d_src, _piped=True)
    sh.tar('xf', '-', '-C', di, _in=tar_command)
    log.info('copied', src=d_src, into=di)

    with sh.pushd(d_src):
        breakpoint()  # FIXME BREAKPOINT
        sh.git('add', '.')
        sh.git('commit', '-am', f'flux: initial commit\n\n{tmpl_url}\n->\n{into_repo}')
        sh.git('push')


class flux:
    prepare_repo = prepare_repo
    install = install
