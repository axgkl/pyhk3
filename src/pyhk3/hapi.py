from .tools import die, env, log, need_env, run, exists, os
import requests
from .cache import cache, nil

E = need_env
base = 'https://api.hetzner.cloud/v1'

icons = {
    'networks': '🖧 ',
    'ssh_keys': '🔑',
    'servers': '🖥️',
    'load_balancers': '🌐',
    'images': '🐧',
    'volumes': '💾 ',
}


def headers():
    api_token = env('HCLOUD_TOKEN_WRITE')
    if not api_token:
        api_token = need_env('HCLOUD_TOKEN')
    return {'Authorization': f'Bearer {api_token}', 'Content-Type': 'application/json'}


def safe(r):
    try:
        return r.json()
    except Exception:
        return {'txt': r.text}


class hapi:
    def get(path):
        v = cache.get(path)
        if v != nil:
            return v
            # return log.debug('Cache hit', path=path) or v
        r = requests.get(f'{base}/{path}', headers=headers())
        r = cache.cache[path] = r.json()[path]
        return r

    def delete(path, id):
        log.info('HApi delete', path=path, id=id)
        r = requests.delete(f'{base}/{path}/{id}', headers=headers())
        if not r.status_code < 300:
            die('HApi delete failed', path=path, id=id, status_code=r.status_code)
        cache.clear(path)

    def post(path, data):
        i = icons.get(path, '')
        if i:
            log.info(f'{i} Create {path[:-1]}', **data)
        else:
            log.info('HApi post', path=path, **data)
        r = requests.post(f'{base}/{path}', headers=headers(), json=data)
        if not r.status_code < 300:
            die('HApi post failed', path=path, **safe(r))
        cache.clear(path)
        return r


def ips(name, no_die=False):
    S = by_name('servers', name)
    if not S:
        if no_die:
            return
        die('Server not found', name=name)
    ip = (S['public_net']['ipv4'] or {}).get('ip')
    priv = (S['private_net'][0] or {}).get('ip')
    return dict(pub=ip, priv=priv)


def by_name(typ, name, short=True, multi=False):
    N = E('NAME')
    if short and not name.startswith(N + '-'):
        name = E('NAME') + '-' + name
    r = [x for x in hapi.get(typ) if x['name'] == name]
    if r and len(r) > 1 and not multi:
        die(f'Multiple {typ} found', name=name)
    return r[0] if r else None
