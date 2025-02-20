import os, sys
import json
from .tools import T0, die, log, now, shw, called
from inspect import signature as sig
from functools import partial
from .create import create, hk3s
from .do import do, recover
from rich.console import Console
from rich.tree import Tree

console = Console()


B = lambda a: f'\x1b[1m{a}\x1b[0m'
L = lambda a: f'\x1b[2m{a}\x1b[0m'
D = lambda a: L((getattr(a, '__doc__', '') or '').strip().split('\n', 1)[0])


def tc(cls):
    return f'{B(cls.__name__)} {D(cls)}'


def tv(fnc):
    return f'{fnc.__name__} {D(fnc)}'


def cls_help(cls, inittree=None):
    tree = inittree or Tree(tc(cls))
    for k in [e for e in dir(cls) if not e.startswith('_')]:
        v = getattr(cls, k)
        if isinstance(v, type):
            tr = tree.add(f'{B(k)} {D(v)}')
            cls_help(v, tr)
            continue
        if not isinstance(v, list):
            tree.add(f'{B(k)} {tv(v)}')
            continue
        tr = tree.add(B(k))
        for m in v:
            tr.add(tv(m))
    if not inittree:
        console.print(tree)
        sys.exit(0)


class pyhk3:
    create = create
    do = do
    recover = recover
    hk3s = hk3s


def create_partial(funcs, args, argv, x):
    """the last func in a argv list may have arguments which we map here to a partial of that func"""
    args.pop(0)
    l = funcs
    if isinstance(l[-1], list):
        l = l[-1]
    kw, varg = {}, ()
    for _, p in sig(l[-1]).parameters.items():
        if int(p.kind) == 1:  # positional_or_keyword
            varg += (args.pop(0),)
        elif int(p.kind) == 2:  # vararg
            varg += tuple(args)
            args.clear()
    if not args:
        l[-1] = partial(l[-1], *varg, **kw)
        return zip(argv, funcs, strict=True)
    die('Unsupported', cmd=x)


def funcs(cls, args):
    funcs = []
    argv = []
    for x in args:
        f = getattr(cls, x, None)
        if not f:
            if not funcs:
                die('Unsupported', cmd=x)
            return create_partial(funcs, args, argv, x)
        funcs.append(f)
        argv.append(x)
    return zip(argv, funcs, strict=True)


def run_cls(cls, args):
    if not args or args[0] in {'help', '--help', '-h'}:
        cls_help(cls)

    for n, f in funcs(cls, args):
        log.info(f'🟧 {n}')
        if not isinstance(f, list):
            f = [f]
        for g in f:
            lastr = shw(g)
    acts = ' '.join(called)
    log.info(f'🟩 Done: {acts} [{round((now() - T0) / 1000.0, 2)}s]')
    return lastr


def main():
    if not len(sys.argv) > 1 or sys.argv[1] in {'help', '--help', '-h'}:
        cls_help(pyhk3)

    a = sys.argv[1]
    c = getattr(pyhk3, a, None)
    if c is None:
        die('Unsupported', cmd=a)
    r = run_cls(c, sys.argv[2:])
    print_result(r)


def print_result(r):
    if not r:
        return
    if isinstance(r, (dict, list, tuple)):
        try:
            r = json.dumps(r, indent=2, default=str)
        except Exception:
            pass
    print(r)


if __name__ == '__main__':
    main()
