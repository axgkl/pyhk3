from ipaddress import ip_address
from .hapi import ips
from .tools import log, ssh, need_env as E
from functools import partial
import sh


def ips_of_host(name):
    """name either ip or hostname"""
    try:
        if ip_address(name).is_private:
            priv = name
            pub = priv = ips('proxy')['pub']
        else:
            priv = pub = name
    except ValueError:
        priv = pub = ips(name)['pub']
        if not priv:
            pub = priv = ips('proxy')['pub']
            priv = ips(name)['priv']
    return pub, priv


def ssh_add_no_hostkey_check(args):
    args.insert(0, 'UserKnownHostsFile=/dev/null')
    args.insert(0, '-o')
    shc = 'StrictHostKeyChecking'
    for n, a in zip(range(len(args)), args, strict=True):
        if a.startswith(shc):
            args[n] = f'{shc}=no'
            return


def port_forward():
    fwd = f'{kubecfg_fwd_port}:127.0.0.1:6443'
    run_remote('master1', 'htop', '-d', '50', _term=True, _fwd=fwd)


def run_remote(name, *cmd, _fwd=None, _term=False, _fg=True):
    """ssh to servers, e.g. ssh proxy [cmd]. autovia via proxy built in."""
    log.debug('Run remote', name=name, cmd=cmd)
    ip_pub, ip = ips_of_host(name)
    args = ssh(ip_pub, cmd='args')
    if ip != ip_pub:
        ssh_add_no_hostkey_check(args)
        args.insert(-1, '-J')
        args.append(f'root@{ip}')
        # clearip(ip)
    if _term:
        args.insert(0, '-t')
    if _fwd:
        args.insert(0, _fwd)
        args.insert(0, '-L')
    args.extend(list(cmd))
    return sh.ssh(args, _fg=_fg)  # this can be redirected w/o probs


kubecfg_fwd_port = int(E('HK_HOST_NETWORK')) + 6443

get_remote = partial(run_remote, _fg=False)
