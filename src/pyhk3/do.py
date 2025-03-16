import yaml
import os
from .defaults import envdefaults
from .tools import env, confirm
from .create import hk3s, tools, local
from .hapi import by_name, hapi, ips, need_env
from .tools import die, log, shw, ssh
from .ssh import port_forward, get_remote, run_remote

E = need_env
clearip = tools.clear_ip_from_known_hosts


def delete(name):
    """Deleting objects by name, via hapi"""
    if name == 'all':
        N = E('NAME')
        r = [x['name'] for x in hapi.get('servers') if x['name'].startswith(N + '-')]
        confirm(f'Delete {r}')
        return [delete(i) for i in r]

    S = by_name('servers', name)
    if not S:
        return log.info('Not found', name=name)
    return hapi.delete('servers', S['id'])


class recover:
    """When proxy died"""

    def kubeconfig():
        """rebuild a kubeconfig from the existing masters' k3s.yaml files"""
        y = []
        N = need_env('NAME')
        for i in range(1, 6):
            n = f'{N}-master{i}'
            ip = ips(n, no_die=True)
            if not ip:
                break
            kubecfg = get_remote(n, 'cat', '/etc/rancher/k3s/k3s.yaml')
            if not kubecfg:
                die('No k3s.yaml found on master', name=n)
            kubecfg = kubecfg.replace(
                'https://127.0.0.1:6443', f'https://{ip["priv"]}:6443'
            )
            kubecfg = kubecfg.replace('default', n)
            y.append(kubecfg)
        kc = [yaml.safe_load(i) for i in y]
        d = kc[0]
        for n in 'clusters', 'users', 'contexts':
            for k in kc[1:]:
                d[n].append(k[n][0])
        kubecfg = yaml.safe_dump(d)
        ip = ips('proxy')['pub']
        run_remote(ip, 'mkdir', '-p', '/root/.kube')
        ssh(ips('proxy')['pub'], cmd='tee /root/.kube/config', input=kubecfg)
        s = get_remote(ip, 'kubectl', 'get', 'nodes')
        if 'master1' not in s:
            die('Kubeconfig not working', output=s)
        print(s)
        log.info('Kubeconfig recovered')

    def hk3sconfig():
        """Rebuilt the config from environ and transfer to proxy"""
        shw(hk3s.recover_config)


def show_env(match=''):
    for k in sorted(envdefaults.__dict__):
        if k[0] != '_' and match in k.lower():
            kl = k.lower()
            v = env(k)
            if 'token' in kl or 'secret' in kl or 'pass' in kl:
                v = v[:4] + '*' * min(50, (len(v) - 4))
            print(f'{k}={v}')


def namespace_force_delete(namespace):
    """Force delete a namespace. Last result when delete ns got stuck"""
    kw = {}
    if namespace == 'flux-system':
        kw['hint'] = 'use "flux uninstall" instead'
    cmd = f"kubectl get namespace {namespace} -o json | jq '.spec.finalizers=[]' | kubectl replace --raw /api/v1/namespaces/{namespace}/finalize -f -"
    log.info('About brutally delete a namespace', cmd=cmd, **kw)
    confirm(f'Force delete ns {namespace}?', default=False)
    os.system(cmd)
    log.info('Namespace deleted brutally')
    cmd = f'kubectl api-resources --verbs=list --namespaced -o name | xargs -n 1 kubectl get -n {namespace}'
    log.info(cmd, wait_confirm=True, hint='possible long list upcoming')
    confirm('Listing now all remaining resources', default=True)
    os.system(cmd)


class do:
    ssh = run_remote
    delete = delete
    download_kubectl = local.download_kubectl
    port_forward = port_forward
    show_env = show_env
    ns_del_force = namespace_force_delete
