from .tools import die, need_env, log
import requests


class providers:
    class digitalocean:
        @classmethod
        def api(cls, pth, meth=requests.get, data=None):
            basedomain = need_env('DOMAIN').split('.', 1)[1]  # axlc.net
            token = need_env('DNS_API_TOKEN')
            _ = 'application/json'
            headers = {'Content-Type': _, 'Authorization': f'Bearer {token}'}
            url = f'https://api.digitalocean.com/v2/domains/{basedomain}/{pth}'
            if data:
                r = meth(url, headers=headers, json=data)
            else:
                r = meth(url, headers=headers)
            if not r.status_code < 300:
                die('digitalocean API error', status=r.status_code, url=url)
            if not meth == requests.delete:
                return r.json()

        @classmethod
        def dns_wildcard_add(cls, ip, dom, subdom):
            l = [e for e in cls.list() if e['name'] == f'*.{subdom}']
            if l:
                if l[0]['data'] == ip:
                    return log.info('DNS wildcard already set', ip=ip, subdom=subdom)
                cls.api(pth=f'records/{l[0]["id"]}', meth=requests.delete)
            ttl = int(need_env('DNS_TTL', 60))
            d = dict(type='A', name=f'*.{subdom}', data=ip, ttl=ttl)
            r = cls.api(pth='records', meth=requests.post, data=d)
            log.info('DNS wildcard added', **r['domain_record'])

        @classmethod
        def list(cls):
            r = cls.api('records').get('domain_records', [])
            log.debug(
                'DigitalOcean records',
                records=[e['name'] for e in r if not e['name'] == '@'],
            )
            return r


def dns_wildcard_add(ip):
    prov = need_env('DNS_PROVIDER')
    wildcard_add = getattr(providers, prov)
    if not wildcard_add:
        return log.error('Unknown DNS provider', provider=prov)
    wildcard_add = wildcard_add.dns_wildcard_add
    dom = need_env('DOMAIN')
    l = dom.split('.')
    subdom, dom = l[0], '.'.join(l[1:])
    return wildcard_add(ip, dom, subdom)
