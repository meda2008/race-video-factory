# -*- coding: utf-8 -*-
"""反汇编 pyc 中指定函数，带行号。"""
import marshal, sys, dis, io

PYC = r"C:\Users\medam\.workbuddy\skills\finance-ranking-video\scripts\__pycache__\run.cpython-313.pyc"
with open(PYC, 'rb') as f:
    code = marshal.loads(f.read()[16:])

want = sys.argv[1] if len(sys.argv) > 1 else '_topic_pipeline'

def find(co, name):
    if co.co_name == name:
        yield co
    for c in co.co_consts:
        if hasattr(c, 'co_name'):
            yield from find(c, name)

buf = io.StringIO()
for co in find(code, want):
    buf.write('### %s  args=%s\n' % (co.co_name, list(co.co_varnames[:co.co_argcount])))
    last = None
    for ins in dis.get_instructions(co, show_caches=False):
        ln = ins.starts_line
        if ln and ln != last:
            buf.write('\n%4d: ' % ln)
            last = ln
        elif ln is None:
            buf.write('     ')
        arg = ins.argrepr
        buf.write('   %-28s %s\n' % (ins.opname, arg if arg else ('' if ins.arg is None else ins.arg)))
    buf.write('\n')
sys.stdout.write(buf.getvalue())
