from .tools import (
    confirm,
    die,
    exists,
    log,
    need_env,
    os,
    read_file,
    render_env_into,
    run,
    ssh,
    write_file,
)
from .hapi import hapi, ips, cache
from .dns import dns_wildcard_add
import sys
import socket
import time
import json
import shutil
from .ssh import get_remote, kubecfg_fwd_port

from .assets.create_templ import T_INST_TOOLS_PROXY, T_CADDY, T_UNIT_FWD, T_SSHD

E = need_env

netname = lambda: f'ten-{E("HK_HOST_NETWORK")}'

here = os.path.dirname(__file__)


def linefeed():
    print('', file=sys.stderr)


class local:  # requirements
    def ensure_ssh_key_local():
        """Ensures local $FN_SSH_KEY pair exists, used when creating proxy"""
        fn = E('FN_SSH_KEY')
        if fn.endswith('.pub'):
            log.die('SSH key file should not end with .pub', fn=fn)
        fnp = fn + '.pub'
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        if not exists(fn):
            log.warn('Creating SSH key', fn=fn)
            run(['ssh-keygen', '-q', '-t', 'ecdsa', '-N', '', '-f', fn])
        if not exists(fnp):
            run(['ssh-keygen', '-y', '-f', fn], stdout=fnp)
        os.chmod(fn, 0o600)
        log.debug('Have local SSH key', fn=fn, fnp=fnp)

    def download_kubectl():
        fn_dflt = E('HOME') + '/.kube/config'
        d = E('HOME') + '/.kube'
        fn = d + '/' + E('NAME')
        os.makedirs(d, exist_ok=True)
        c = get_remote('proxy', 'cat', '/root/.kube/config')
        if not c:
            die('No kubeconfig found on proxy')
        l = c.splitlines()
        c = []
        while l:
            c.append(l.pop(0))
            if c[-1].lstrip().startswith('server:'):
                line = c[-1].split(':')
                line[2] = '//127.0.0.1'
                line[3] = str(kubecfg_fwd_port)
                c[-1] = ':'.join(line)
        c = '\n'.join(c)
        o = read_file(fn, 'x')
        if os.path.islink(fn_dflt):
            os.unlink(fn_dflt)
        elif os.path.exists(fn_dflt):
            log.warn('Moving existing kubeconfig', fn_dflt=fn_dflt)
            shutil.move(fn_dflt, f'{fn_dflt}-{time.ctime()}')

        if o.strip() == c.strip():
            log.info('Kubeconfig already up to date')
        else:
            if 'https://' in o:
                fno = f'{fn}-{time.ctime()}'
                write_file(fno, o)
                log.info('backed up old kubeconfig', fn=fno)
            write_file(fn, c)
        os.symlink(fn, fn_dflt)
        log.info('have kubeconfig', fn=fn, symlinked=fn_dflt)


class proxy_:
    """Creates a Linux server acting as SSH proxy and LB - Only one with Pub IP"""

    def ensure_host_network():
        """Private network for all hosts"""
        nr = int(E('HK_HOST_NETWORK', '1'))
        r = hapi.get('networks')
        if netname() in [x['name'] for x in r]:
            return
        net = f'10.{nr}.0.0'
        sn = [{'ip_range': f'{net}/24', 'network_zone': 'eu-central', 'type': 'cloud'}]
        m = {
            'name': netname(),
            'ip_range': f'{net}/16',
            'expose_routes_to_vswitch': False,
            'subnets': sn,
            'labels': {'environment': 'dev', 'k3s': E('NAME')},
        }
        hapi.post('networks', data=m)

    def ensure_server():
        """Creates the server acting as SSH proxy and LB"""
        return tools.ensure_server(
            'proxy', E('HK_PROXY_TYPE'), E('HK_PROXY_IMG'), E('HK_LOCATION')
        )

    def ensure_default_route_via_proxy():
        """Ensures default route iof priv net is via proxy"""
        nets = hapi.get('networks')
        n = [x for x in nets if x['name'] == netname()]
        if not n:
            die('Network not found', name=netname())
        ip = ips('proxy')['priv']
        id = n[0]['id']
        routes = n[0]['routes']
        routes = [r for r in routes if r['destination'] == '0.0.0.0/0']
        d = lambda i: {'destination': '0.0.0.0/0', 'gateway': i}
        if routes:
            i = routes[0].get('gateway')
            if i == ip:
                return
            hapi.post(f'networks/{id}/actions/delete_route', data=d(i))
        hapi.post(f'networks/{id}/actions/add_route', data=d(ip))

    def ensure_is_ip_forwarder():
        """Persists and starts ip forwarding and NAT on proxy"""
        svc = 'ip_forwarder.service'
        ip = ips('proxy')['pub']
        have = ssh(ip, cmd='ls /etc/systemd/system')
        if svc in have:
            return
        u = T_UNIT_FWD(E('HK_HOST_NETWORK'))
        have = ssh(ip, cmd=f'tee /etc/systemd/system/{svc}', input=u)
        u = 'systemctl enable --now ip_forwarder'
        have = ssh(ip, input=u)

    def postinstall():
        """Installs kubectl, helm, kubectx, hetzner-k3s via binenv plus caddy/l4 proxy"""
        ip = ips('proxy')['pub']
        ssh(ip, input=T_SSHD)
        t = render_env_into(T_INST_TOOLS_PROXY)
        ssh(ip, input=t, capture_output=False)
        url = E('URL_CADDY')
        ssh(ip, cmd=f'curl -s -L -o /root/caddy "{url}"', bg=True, capture_output=False)

    def configure_caddy():
        """Configures Caddy as a Layer 4 proxy into the cluster, incl. proxy protocol v2"""
        s = {}
        for p in [80, 443]:
            # 🧧 its a service and we use a secure master one. works but not optimal:
            dials = [f'10.{E("HK_HOST_NETWORK")}.0.5:{p + 30000}']
            h = {
                'handler': 'proxy',
                'proxy_protocol': 'v2',
                'upstreams': [{'dial': dials}],
            }
            s[f'port{p}'] = {
                'listen': [f':{p}', f'[::]:{p}'],
                'routes': [{'handle': [h]}],
            }
        c = {
            'logging': {
                'sink': {'writer': {'output': 'stdout'}},
                'logs': {'default': {'level': 'DEBUG'}},
            },
            'apps': {'layer4': {'servers': s}},
        }
        ssh(ips('proxy')['pub'], input=T_CADDY(json.dumps(c)), capture_output=False)


class tools:
    def ensure_ssh_key_known_to_hetzner():
        have = hapi.get('ssh_keys') or []
        fps = set([k['fingerprint'] for k in have])
        fp = E('FN_SSH_KEY') + '.pub'
        r = run(
            ['ssh-keygen', '-l', '-E', 'md5', '-f', fp],
            capture_output=True,
            text=True,
        )
        r = r.split(':', 1)[1].split()[0]
        if r in fps:
            return [k['name'] for k in have if k['fingerprint'] == r][0]
        n = E('NAME')
        if n in [k['name'] for k in have]:
            msg = f'proceed to delete and re-add the SSH key {n}'
            if not confirm(msg, default=False):
                die('unconfirmed')
            f = [k['id'] for k in have if k['name'] == n]
            r = hapi.delete('ssh_keys', f[0])
        r = hapi.post('ssh_keys', data={'name': n, 'public_key': open(fp).read()})
        return n

    def ensure_server(shortname, typ, img, loc):
        key_name = tools.ensure_ssh_key_known_to_hetzner()
        name = E('NAME') + '-' + shortname
        have = hapi.get('servers') or []
        if name not in [x['name'] for x in have]:
            nid = [x['id'] for x in hapi.get('networks') if x['name'] == netname()]
            if not nid:
                die('No network found', name=netname())
            data = dict(
                name=name,
                server_type=typ,
                image=img,
                location=loc,
                ssh_keys=[key_name],
                networks=nid,
                public_net=dict(enable_ipv4=True, enable_ipv6=True),
                labels=dict(environment='dev', k3s=E('NAME')),
            )
            while True:
                server = hapi.post('servers', data=data)
                srv_id = server.json()['server']['id']
                time.sleep(2)
                ip = ips(shortname)['pub']

                log.info('Server ordered - waiting for ssh 🕐', name=name, ip=ip)
                tools.clear_ip_from_known_hosts(ip)
                if not tools.wait_ssh_port(ip, 22):
                    hapi.delete('servers', srv_id)
                    continue
                linefeed()
                log.info('Server is up - waiting for ip priv', name=name, ip=ip)
                cache.active = False
                while True:
                    p = ips(shortname)['priv']
                    if p:
                        log.info(f'have priv ip {p}')
                        break
                    time.sleep(2)
                cache.active = True
                r = ssh(ip, port=22, cmd='curl -s ipinfo.io/ip')
                linefeed()
                if r == ip:
                    break
                msg = f'Tough luck - our ip {ip} seems to be not acceptable by some internet services. Trying again.'
                log.warn(msg)
                hapi.delete('servers', srv_id)

        log.info('Server is up', name=name, **ips(shortname))

    def wait_ssh_port(host, port, max_retries=150, dt=2):
        buffer = ''
        for _ in range(max_retries):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(dt)
                    s.connect((host, port))
                    while True:
                        data = s.recv(1024).decode('utf-8')
                        if not data:
                            break
                        buffer += data
                        if 'SSH' in buffer:
                            return True
            except (socket.error, socket.timeout) as _:
                print('.', end='', flush=True, file=sys.stderr)
                time.sleep(dt)
        msg = f'Failed to find "SSH" in the reply from {host}.'
        log.warning(msg, timeout=dt * max_retries)
        return False

    def clear_ip_from_known_hosts(ip):
        ip = ip + ' '
        fn = os.path.expanduser('~/.ssh/known_hosts')
        h = read_file(fn, dflt='')
        if ip not in h:
            return
        hn = [l for l in h.splitlines() if not l.startswith(ip)]
        if hn != h:
            write_file(fn, '\n'.join(hn), mkdir=1)


class hk3s:
    def render_config():
        """required standalone for recovering the proxy"""
        ip = ips('proxy', no_die=True)
        key_proxy = '# </root/.ssh/id_ed25519.pub of proxy server - not created yet>'
        if ip:
            ip = ip['pub']
            key_proxy = ssh(ip, cmd='cat /root/.ssh/id_ed25519.pub')
        dtmpl = f'{here}/assets'
        tmpl = E('HK_CFG_TMPL', '') or f'{dtmpl}/hk3s.yml'
        pmpl = E('HK_CFG_POST', '') or f'{dtmpl}/hk3s_post_create.yml'
        cfg = render_env_into(read_file(tmpl))
        d = dict(key_proxy=key_proxy, key_local=read_file(E('FN_SSH_KEY') + '.pub'))
        return cfg + render_env_into(read_file(pmpl), add=d)

    def recover_config():
        ip = ips('proxy')['pub']
        cfg = hk3s.render_config()
        ssh(ip, cmd='tee /root/config.yml', input=cfg)
        return ip

    def install():
        """Renders hetzner-k3s config, copies to proxy and runs the tool"""
        hk3s.recover_config()
        ip = ips('proxy')['pub']
        v = os.environ.get('HCLOUD_TOKEN')
        os.environ['HCLOUD_TOKEN'] = E('HCLOUD_TOKEN_WRITE')
        cmd = 'kubectl get nodes 2>/dev/null && echo "Skipping install - already running" || '
        cmd += 'hetzner-k3s create --config /root/config.yml'
        ssh(ip, cmd=cmd, capture_output=False, send_env=['HCLOUD_TOKEN'])
        os.environ['HCLOUD_TOKEN'] = v


class dns:
    def add_subdomain():
        """Points a whole subdomain to the proxy server"""
        return dns_wildcard_add(ips('proxy')['pub'])


class create:
    """Create New Infrastructure"""

    proxy = [
        local.ensure_ssh_key_local,
        proxy_.ensure_host_network,
        proxy_.ensure_server,
        proxy_.ensure_default_route_via_proxy,
        proxy_.ensure_is_ip_forwarder,
        proxy_.postinstall,
    ]
    k3s = hk3s.install
    proxylb = proxy_.configure_caddy
    dns = dns.add_subdomain


if __name__ == '__main__':
    main()
