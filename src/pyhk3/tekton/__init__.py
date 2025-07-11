import os, yaml
import shutil
from ..kubectl import port_fwd
from ..ssh import ensure_forward
from ..tools import require_cmd, confirm, die, log, read_file, run, const, shw, write_file
from ..tools import need_env as E
from ..tools import cmd, 𝛌
# from ..flux import tools

d_our_repo = E('FLUX_REPO', '.')
req_cmds = cmd('kubectl', 'sops', 'helm', use='--help') + cmd('age', 'git', 'flux')

d_ymls = os.path.abspath(os.path.dirname(__file__)) + '/yamls'


class tekton:
    ensure_requirements = lambda: require_cmd(*req_cmds)
    port_forward = λ(port_fwd, 'tekton-pipelines', 'svc/tekton-dashboard', 9097)
    reconcile = lambda: run('flux reconcile kustomization infra-tekton -n flux-system')

    def install():
        """Install Tekton using Flux.

        Just downloaded operator.yaml from here: https://tekton.dev/docs/operator/install/

        """
        d_our_repo = tools.get_clean_repo()
        fn_entry = d_our_repo + '/clusters/production/infrastructure.yaml'
        infra = read_file(fn_entry, '')
        if 'infra-tekton' in infra:
            return log.info('have tekton already in the repo - skipping for idempotency')
        ensure_forward()
        tools.tar_pipe(d_ymls, d_our_repo)
        tools.git(d_our_repo, add='.', msg='Tekton setup', push=False)
        write_file(fn_entry, infra + T)
        tools.git(d_our_repo, add='.', msg='Tekton reference', push=True)
        log.info('Tekton installation configured. Waiting for Flux to apply changes...')

    def remove_from_cluster():
        d_our_repo = tools.get_clean_repo()
        fn_entry = d_our_repo + '/clusters/production/infrastructure.yaml'
        cmt = False
        if os.path.exists(fn_entry):
            docs = read_file(fn_entry, '').split('\n---\n')
            docs = '\n---\n'.join([doc for doc in docs if 'infra-tekton' not in doc])
            cmt = True
            with open(fn_entry, 'w') as f:
                f.write(docs + '\n')
        d = d_our_repo + '/infrastructure/tekton'
        if os.path.exists(d):
            shutil.rmtree(d)
            cmt = True
        cmt and tools.git(d_our_repo, add='.', msg='Tekton removed', push=True)
        for l in [
            """for crd in $(kubectl get crd | grep -i tekton | awk '{print $1}'); do kubectl patch crd $crd -p '{"metadata":{"finalizers":[]}}' --type=merge; done""",
            """kubectl get crd | grep -i tekton | awk '{print $1}' | xargs -I {} kubectl delete crd {}""",
            """kubectl get ns | grep tekton | awk '{print $1}' | xargs -I {} kubectl delete ns {}""",
            'echo "checking if all gone:"',
            'kubectl get all --all-namespaces | grep -i tekton',
            'kubectl get crd| grep -i tekton',
        ]:
            log.info(l) or os.system(l)
        log.info('Removed all tekton from your cluster and flux repo')


T = """
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: infra-tekton-operator
  namespace: flux-system
spec:
  dependsOn:
    - name: infra-controllers
  interval: 1h
  retryInterval: 1m
  timeout: 5m
  sourceRef:
    kind: GitRepository
    name: flux-system
  path: ./infrastructure/tekton
  prune: true
  wait: true
  decryption:
    provider: sops
    secretRef:
      name: sops-age
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: infra-tekton-config
  namespace: flux-system
spec:
  dependsOn:
    - name: infra-tekton-operator  # Wait for operator to be ready
  interval: 1h
  retryInterval: 1m
  timeout: 5m
  sourceRef:
    kind: GitRepository
    name: flux-system
  path: ./infrastructure/tekton/config
  prune: true
  wait: true
"""
