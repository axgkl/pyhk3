# https://cheatography.com/linux-china/cheat-sheets/justfile/
set dotenv-filename := 'environ'
set dotenv-load := true
set dotenv-required := true
set export
set unstable
set script-interpreter := ['uv', 'run']
alias c := create-cluster
alias cfg := render-config
alias t := test
alias p := pyhk3
alias pf := port-forward
alias elk := download-kubectl

default:
  @just --list

pyhk3 *ARGS:
  uv run pyhk3 {{ARGS}}

do *ARGS:
  just p do {{ARGS}}

ssh *ARGS:
  just p do ssh {{ARGS}}

render-config:
  just p hk3s render_config
  
port-forward:
  just p do port_forward

[confirm('Sure to destroy all servers of the cluster?')]
rm:
  just p do remove all



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

test:
  just render-config
  uv run pytest ./tests/test_setup.py

publish:
  just test
  uv build
  uv publish --token `pass show pypitoken`
