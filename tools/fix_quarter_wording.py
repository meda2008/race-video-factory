# -*- coding: utf-8 -*-
"""修正 A股季度题材的口径描述：
数据是单季值（财报类已做「本期累计 − 上期累计」差分）或季末时点数，
但图例写的是「当年 / 年末」，会让观众误以为是年度数据。

用法：python scripts_local/fix_quarter_wording.py [--dry-run]
"""
import json
import glob
import os
import sys
import shutil
from datetime import datetime

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(WS)

# key -> {字段: (旧, 新)}
FIX = {
    'ashare_profit':     {'legend': ('当年净利润', '当季净利润')},
    'ashare_loss':       {'legend': ('当年净亏损额', '当季净亏损额')},
    'ashare_revenue':    {'legend': ('当年营业总收入', '当季营业总收入'),
                          'subtitle': ('A股营业总收入 2004', 'A股单季营业总收入 2004')},
    'ashare_ocf':        {'legend': ('当年经营性现金流净额', '当季经营性现金流净额'),
                          'subtitle': ('A股经营性现金流净额 2004', 'A股单季经营性现金流净额 2004')},
    'ashare_sellexp':    {'legend': ('当年销售费用', '当季销售费用'),
                          'subtitle': ('A股销售费用 2004', 'A股单季销售费用 2004')},
    'ashare_cash':       {'legend': ('年末货币资金', '季末货币资金'),
                          'subtitle': ('A股货币资金 2004', 'A股货币资金（季末）2004')},
    'ashare_receivable': {'legend': ('年末应收账款', '季末应收账款'),
                          'subtitle': ('A股应收账款 2004', 'A股应收账款（季末）2004')},
}


def main():
    dry = '--dry-run' in sys.argv
    changed = {}
    n = 0
    for f in sorted(glob.glob('topics_registry_*.json')):
        data = json.load(open(f, encoding='utf-8'))
        touched = False
        for t in data.get('topics', []):
            key = t.get('key') or t.get('slug')
            if key not in FIX:
                continue
            p = t.get('params', t)
            for field, (old, new) in FIX[key].items():
                cur = p.get(field) or ''
                if old in cur:
                    nv = cur.replace(old, new)
                    print('  %-18s %s' % (key, field))
                    print('      - %s' % cur)
                    print('      + %s' % nv)
                    if not dry:
                        p[field] = nv
                    touched = True
                    n += 1
                else:
                    print('  ⚠ %-16s %s 未找到「%s」：%s' % (key, field, old, cur))
        if touched:
            changed[f] = data

    print('\n共 %d 处改动，涉及 %d 个文件' % (n, len(changed)))
    if dry or not changed:
        print('(dry-run，未写入)' if dry else '(无改动)')
        return
    bdir = os.path.join('data', '_backup_registry_pre_qw',
                        datetime.now().strftime('%Y%m%d_%H%M%S'))
    os.makedirs(bdir, exist_ok=True)
    for f in changed:
        shutil.copy2(f, os.path.join(bdir, os.path.basename(f)))
    for f, d in changed.items():
        with open(f, 'w', encoding='utf-8') as fh:
            json.dump(d, fh, ensure_ascii=False, indent=2)
    print('备份到 %s' % os.path.abspath(bdir))
    print('已写入')


if __name__ == '__main__':
    main()
