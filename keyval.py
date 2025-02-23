"""
Custom calc-ed values for <key>='py:<this module path>' constructs
❗ module path w/o '.py'

Evaluated only once, not per key.
"""

try:
    from mysecrets import sec  # whatever
except ImportError:
    sec = {}


DNS_API_TOKEN = sec.get('DNS_API_TOKEN', '...')
DOMAIN = sec.get('DOMAIN', 'cluster.company.net')
EMAIL = sec.get('EMAIL', 'my.email@company.net')
FN_SSH_KEY = sec.get('FN_SSH_KEY', '~/.ssh/hetzner-cluster')
GITOPS_HOST = sec.get('GITOPS_HOST', 'gitlab.company.com')
GITOPS_TOKEN = sec.get('GITOPS_TOKEN', '...')
HCLOUD_TOKEN = sec.get('HCLOUD_TOKEN', '...')
HCLOUD_TOKEN_WRITE = sec.get('HCLOUD_TOKEN_WRITE', '...')

# delivering a pass value is also possible:
GITOPS_FLUX_PRIV_SECRET = sec.get('GITOPS_FLUX_PRIV_SECRET', 'pass:my/flux_priv_secret')
