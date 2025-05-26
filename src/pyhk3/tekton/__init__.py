import os

from ..ssh import ensure_forward
from ..tools import require_cmd, confirm, die, log, read_file, run, const, shw, write_file
from ..tools import need_env as E
from ..tools import cmd
from ..flux import tools

d_our_repo = E('FLUX_REPO', '.')
req_cmds = cmd('kubectl', 'sops', 'helm', use='--help') + cmd('age', 'git', 'flux')

d_ymls = os.path.abspath(os.path.dirname(__file__)) + '/yamls'


class tekton:
    ensure_requirements = lambda: require_cmd(*req_cmds)

    def install():
        """Install Tekton using Flux.

        This will:
        1. Create the necessary directory structure
        2. Set up the Tekton operator
        3. Configure Tekton components
        4. Create a Flux kustomization to manage Tekton
        """
        d_our_repo = tools.get_clean_repo()
        fn_entry = d_our_repo + '/clusters/production/infrastructure.yaml'
        infra = read_file(fn_entry, '')
        if 0 and 'infra-tekton' in infra:
            return log.info('have tekton already in the repo - skipping for idempotency')
        ensure_forward()
        tools.tar_pipe(d_ymls, d_our_repo)
        tools.git(d_our_repo, add='.', msg='Tekton setup', push=False)
        write_file(fn_entry, infra + T)
        tools.git(d_our_repo, add='.', msg='Tekton reference', push=True)
        tools.reconcile()
        log.info('Tekton installation configured. Waiting for Flux to apply changes...')

    def port_forward():
        run('kubectl port-forward -n tekton-pipelines svc/tekton-dashboard 9097:9097')


T = """
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: infra-tekton
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
"""
