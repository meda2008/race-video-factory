# -*- coding: utf-8 -*-
"""从 run.cpython-313.pyc 抽取指定函数的全部常量（含字节码行序），用于重建源码。
用法: python _dump_pyc2.py <func_name> [more...]
"""
import marshal, sys

PYC = r"C:\Users\medam\.workbuddy\skills\finance-ranking-video\scripts\__pycache__\run.cpython-313.pyc"

with open(PYC, 'rb') as f:
    code = marshal.loads(f.read()[16:])

want = set(sys.argv[1:]) or {'_topic_pipeline'}

def brief(v, lim=200):
    if isinstance(v, str):
        return repr(v) if len(v) <= lim else repr(v[:lim - 3] + '...')
    if isinstance(v, (int, float, bool, type(None))):
        return repr(v)
    if isinstance(v, bytes):
        return 'b<%d>' % len(v)
    if isinstance(v, tuple):
        return 'tuple(%d)[%s]' % (len(v), ', '.join(brief(x, 40) for x in v[:8]))
    if isinstance(v, frozenset):
        return 'frozenset(%s)' % sorted(map(str, v))
    if hasattr(v, 'co_name'):
        return '<code %s>' % v.co_name
    return type(v).__name__ + ':' + repr(v)[:60]

def find(co, name, path=''):
    if co.co_name == name:
        yield co, path
    for c in co.co_consts:
        if hasattr(c, 'co_name'):
            yield from find(c, name, path + '/' + co.co_name)

for name in want:
    for co, path in find(code, name):
        print('=' * 70)
        print('FUNC %s  (from %s)  args=%s  firstlineno=%d' % (
            co.co_name, path or '<module>', list(co.co_varnames[:co.co_argcount]), co.co_firstlineno))
        print('  varnames:', co.co_varnames)
        print('  names   :', co.co_names)
        print('  consts  :')
        for i, c in enumerate(co.co_consts):
            print('    [%2d] %s' % (i, brief(c)))
        print()
