from .assets.kubectl import T_NS
from .tools import run, log, add_to_pass, need_env as E, die, env_key_on_missing
from base64 import b64decode as b64
import json
import sh


def port_fwd(ns, svc, port):
    log.info(f'http://127.0.0.1:{port}')
    run(f'kubectl port-forward -n {ns} {svc} {port}:{port}')


def ensure_namespace(namespace: str):
    try:
        return sh.kubectl.get.namespace(namespace)
    except sh.ErrorReturnCode_1:
        n = T_NS % {'namespace': namespace}
        sh.kubectl.apply('-f', '-', _in=n)


def ensure_secret(name, key, ns, envkey=None):
    """Ensuring secret in cluster, creating if missing from:

    - envkey value if set
    - age-keygen  if not

    When envkey is not set and startswith 'pass:' we create pass entry as well
    """
    ensure_namespace(ns)
    ns = ('--namespace', ns)
    env = None
    if envkey:
        env = E(envkey, env_key_on_missing)
    try:
        priv = json.loads(sh.kubectl.get.secret(name, '-o', 'jsonpath={.data}', *ns))
        log.debug('Secret present in cluster', name=name)
    except Exception:
        priv = None
    if priv:
        if not key in priv:
            die(f'Secret {name} is on the cluster but misssing {key}')
        priv = b64(priv[key]).decode('utf-8')

    if priv:
        if env:
            if priv == env:
                log.info('Secret matches with environ', name=name)
            elif env.startswith('pass:'):
                add_to_pass(env, priv)
            elif env != env_key_on_missing:
                m = f'Secret {name} is on the cluster but has different value in env'
                die(m, envkey=envkey, name=name, key=key)
        return priv

    log.warn('Secret not found in cluster - creating', name=name)
    if env and env != env_key_on_missing and env[:5] != 'pass:':
        priv = env
    else:
        log.warn('Secret not found in cluster - creating', name=name)
        priv = sh.age_keygen().strip()  # full on needed in k8s. .split('\n')[-1]
        assert 'AGE-SECRET-KEY' in priv

    _ = f'--from-file={key}=/dev/stdin'
    sh.kubectl.create.secret.generic(name, _, *ns, _in=priv)
    if env.startswith('pass:'):
        add_to_pass(env, priv)

    return priv


def age_pub_from_priv(priv):
    """Return public key from secret"""
    return sh.age_keygen('-y', _in=priv).strip()
