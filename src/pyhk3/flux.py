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


class flux:
    install = install
