from ..ssh import ensure_forward
from ..tools import require_cmd, confirm, die, log, read_file, run, const, shw, write_file
from ..tools import exists, need_env as E
from ..tools import do_git, cmd
import os, sh, shutil, json


d_flux = os.path.abspath(E('FLUX_REPO', '.'))


class git:
    do = do_git

    def create_branch(env, d):
        git.do('branch', env, d=d)
        git.do('push', 'origin', env, d=d)

    def clone():
        env = E('GITOPS_ENV')
        url = f'git@{E("GITOPS_HOST")}:{E("GITOPS_OWNER")}/{E("GITOPS_REPO")}'
        os.makedirs(d_flux, exist_ok=True)
        db = d_flux + '/git'
        if not exists(db):
            git.do('clone', '--bare', url, db)
            _ = '+refs/heads/*:refs/remotes/origin/*'
            git.do('config', 'remote.origin.fetch', _, db, d=db)
            git.do('config', 'push.autoSetupRemote', 'true', d=db)
        return db

    def pull():
        env = E('GITOPS_ENV')
        db = git.clone()
        branches = git.do('branch', '-a', '--format=;%(refname:short);', d=db)
        if not f';{env};' in branches:
            git.create_branch(env, d=db)
        d = d_flux + '/' + env
        if not exists(d):
            git.do('worktree', 'add', f'../{env}', env, d=db)
            git.do('pull', 'origin', env, d=d)
            git.do('branch', f'--set-upstream-to=origin/{env}', env, d=d)
        git.do('pull', d=d)
        return d

    def push(msg=None):
        d = d_flux + '/' + E('GITOPS_ENV')
        if msg:
            git.do('commit', '-am', msg, d=d, _ok_code=[0, 1])
        git.do('push', d=d)

    def get_adder(d):
        def adder(fn, s=None, d=d, **kw):
            if s:
                have = read_file(fn, dflt='')
                kw['mkdir'] = True
                if not have:
                    write_file(f'{d}/{fn}', s, **kw)
                else:
                    if have != s:
                        log.warn('exists and different', fn=fn)
            git.do('add', fn, d=d)

        return adder
