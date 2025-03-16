from ipaddress import ip_address
from .hapi import ips
from .tools import run, log, ssh, die, need_env as E
from subprocess import Popen
from functools import partial
import sh

from time import sleep
import sys


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


def ensure_forward(_chck=False):
    if not _chck:
        log.info('Ensure port forward for kubectl')
    m = f'{E("NAME")}-master1'
    try:
        r = sh.kubectl.get.nodes()
        if m in r:
            return True
        die('Wrong kubernetes cluster', notfound=m, output=r)
    except Exception as ex:
        if 'certificate' in str(ex):
            die('kubectl certificate error', hint='do download_kubectl')
        if _chck:
            return 0
        port_forward(nohup=True)
        for _ in range(10):
            sleep(1)
            print('.', file=sys.stderr, end='')
            if ensure_forward(_chck=True):
                print('')
                return
        die('No tunnel')


def port_forward(nohup=False):
    log.info('Port forward', kubecfg_fwd_port=kubecfg_fwd_port)
    c = ['htop', '-d', '50']
    if nohup:
        c = ['sleep', '3600']
    fwd = f'{kubecfg_fwd_port}:127.0.0.1:6443'
    run_remote('master1', *c, _term=True, _fwd=fwd, _nohup=nohup)


def run_remote(name, *cmd, _fwd=None, _term=False, _fg=True, _nohup=False):
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
    try:
        if _nohup:
            ssh_command = ' '.join(f'"{i}"' for i in args)
            # sh.nohup not working
            return Popen(
                f'nohup ssh {ssh_command} > /dev/null 2> /dev/null &', shell=True
            )
        else:
            r = sh.ssh(args, _fg=_fg)
    except Exception as ex:
        die('ssh failed', name=name, cmd=cmd, ex=ex)
    return r


kubecfg_fwd_port = int(E('HK_HOST_NETWORK')) + 6443

get_remote = partial(run_remote, _fg=False)
