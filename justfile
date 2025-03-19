# https://cheatography.com/linux-china/cheat-sheets/justfile/
set dotenv-filename := 'environ'
set dotenv-load := true
set dotenv-required := true
set export
set unstable
set script-interpreter := ['uv', 'run']
alias c := create-cluster
alias cfg := pyhk3-config
alias t := test
alias p := pyhk3
alias pf := port-forward
alias fk := flux-kubeconform
alias elk := download-kubectl

export FLUX_REPO := 'tmp/our-repo.git'

default:
  @just --list

pyhk3 *ARGS:
  uv run pyhk3 {{ARGS}}

do *ARGS:
  just p do {{ARGS}}

ssh *ARGS:
  just p do ssh {{ARGS}}

pyhk3-config *ARGS:
  just p hk3s render_config
  just p do show_env {{ARGS}}

env *ARGS:
  just p do show_env {{ARGS}}

[confirm('Sure to destroy all servers of the cluster?')]
rm:
  just p do delete all


[confirm('Sure to destroy proxy (if existing) and recreate it?')]
recover-proxy:
  just p do delete proxy
  just p create proxy proxylb dns
  just p recover hk3sconfig
  just p recover kubeconfig

create-cluster:
  just p create proxy k3s proxylb dns

download-kubectl:
  just p do download_kubectl

# enables a port-forward to proxy, so that kubectl, when downloaded, can be used
port-forward:
  just p do port_forward


flux-install:
  just p flux install
  just p flux add_sops_secret
  just p flux add_tmpl 'gh:/fluxcd/flux2-kustomize-helm-example'

flux-uninstall:
  just p flux uninstall

flux-kubeconform:
  cd "$FLUX_REPO" && scripts/validate.sh

test:
  just pyhk3-config
  uv run pytest ./tests/test_setup.py

publish:
  just test
  uv build
  uv publish --token `pass show pypitoken`
