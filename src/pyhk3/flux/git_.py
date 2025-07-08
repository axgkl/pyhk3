from .ssh import ensure_forward
from .tools import require_cmd, confirm, die, log, read_file, run, const, shw, write_file
from .tools import exists, need_env as E
from .tools import cmd
import os, sh, shutil, json


d_flux = os.path.abspath(E('FLUX_REPO', '.'))


class git:
    def do(f, *a, d=None, **kw):
        kw['_cwd'] = d
        if d:
            kw['_cwd'] = d.replace(os.getcwd(), '.')
        log.info(f'git {f} {" ".join(list(a))}', **kw)
        kw['_cwd'] = d
        return getattr(sh.git, f)(*a, **kw)

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
        git.do('pull', d=d)
        return d

    def push():
        git.do('push', d=d_flux + '/' + E('GITOPS_ENV'))

    def get_adder(d):
        def adder(fn, s=None, d=d):
            if s:
                write_file(f'{d}/{fn}', s)
            git.do('add', fn, d=d)

        return adder
