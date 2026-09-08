# -*- coding: utf-8 -*-
"""从 __pycache__/run.cpython-313.pyc 抽取源码骨架，用于重建被截断的 run.py。
输出：函数/类树 + 参数名 + 字符串常量 + 数值常量。
"""
import marshal, importlib.util, sys, dis

PYC = r"C:\Users\medam\.workbuddy\skills\finance-ranking-video\scripts\__pycache__\run.cpython-313.pyc"

with open(PYC, 'rb') as f:
    data = f.read()
code = marshal.loads(data[16:])

def brief(v):
    if isinstance(v, str):
        return repr(v) if len(v) <= 120 else repr(v[:117] + '...')
    if isinstance(v, (int, float, bool, type(None))):
        return repr(v)
    if isinstance(v, bytes):
        return 'b<%d>' % len(v)
    if isinstance(v, tuple):
        return 'tuple(%d)' % len(v)
    return type(v).__name__

def walk(co, depth=0, out=None):
    out = out if out is not None else []
    pad = '  ' * depth
    args = co.co_varnames[:co.co_argcount]
    kw = co.co_varnames[co.co_argcount:co.co_argcount + co.co_kwonlyargcount]
    out.append('%sDEF %s(%s%s)%s  [stack=%d nconst=%d]' % (
        pad, co.co_name, ', '.join(args),
        (', *' + ', '.join(kw)) if kw else '',
        ' @%d' % co.co_firstlineno, co.co_stacksize, len(co.co_consts)))
    strs, nums = [], []
    for c in co.co_consts:
        if isinstance(c, str) and len(c.strip()) > 0:
            strs.append(c)
        elif isinstance(c, (int, float)) and not isinstance(c, bool):
            nums.append(c)
    if strs:
        for s in strs[:40]:
            out.append('%s  S: %s' % (pad, brief(s)))
        if len(strs) > 40:
            out.append('%s  S: ...(+%d)' % (pad, len(strs) - 40))
    if nums:
        out.append('%s  N: %s' % (pad, ', '.join(repr(n) for n in nums[:30])))
    names = [n for n in co.co_names]
    if names:
        out.append('%s  G: %s' % (pad, ', '.join(names[:60])))
    for c in co.co_consts:
        if hasattr(c, 'co_name'):
            walk(c, depth + 1, out)
    return out

lines = walk(code)
sys.stdout.write('\n'.join(lines))
print()
print('# LINES=%d  (module firstlineno=1, max line: %d)' % (len(lines), max(
    [c.co_firstlineno for c in [code]] + [0])))
