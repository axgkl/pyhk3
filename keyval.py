"""
Custom calc-ed values for <key>='py:<this module path>' constructs
❗ module path w/o '.py'

Evaluated only once, not per key.
"""

try:
    from mysecrets import sec  # whatever
except ImportError:
    sec = {}


DOMAIN = sec.get('DOMAIN', 'cluster.company.net')
EMAIL = sec.get('EMAIL', 'my.email@company.net')
GITOPS_HOST = sec.get('GITOPS_HOST', 'gitlab.company.com')

DNS_API_TOKEN = sec.get('DNS_API_TOKEN', '...')
GITOPS_TOKEN = sec.get('GITOPS_TOKEN', '...')
HCLOUD_TOKEN = sec.get('HCLOUD_TOKEN', '...')
HCLOUD_TOKEN_WRITE = sec.get('HCLOUD_TOKEN_WRITE', '...')
