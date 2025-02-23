from .assets.kubectl import T_NS, T_SECRET
from .tools import run
import sh


def ensure_namespace(namespace: str):
    try:
        sh.kubectl('get', 'namespace', namespace)
        return
    except sh.ErrorReturnCode_1:
        n = T_NS % {'namespace': namespace}
        sh.kubectl('apply', '-f', '-', _in=n)


def add_secret(name: str, namespace: str, data: str):
    breakpoint()  # FIXME BREAKPOINT
    run(f'kubectl create namespace {name}')
