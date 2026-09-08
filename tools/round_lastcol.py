# -*- coding: utf-8 -*-
"""把指定 CSV 的最后一列（最新年）四舍五入到 N 位小数，避免 WDI 原始值携带过长小数。
用法：python round_lastcol.py <key1> <key2> ... [--dec 2]
"""
import argparse, csv, glob, os
WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def resolve(key):
    for d in ('data/topics_csv', 'topics'):
        p = os.path.join(WS, d, key + '.csv')
        if os.path.exists(p):
            return p
    hits = glob.glob(os.path.join(WS, '**', key + '.csv'), recursive=True)
    return hits[0] if hits else None
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('keys', nargs='+')
    ap.add_argument('--dec', type=int, default=2)
    a = ap.parse_args()
    for k in a.keys:
        p = resolve(k)
        if not p:
            print('跳过(未找到)', k); continue
        rows = list(csv.reader(open(p, encoding='utf-8-sig', newline='')))
        years = rows[0][1:]
        last = years[-1]
        cnt = 0
        for r in rows[1:]:
            if len(r) < 2 or not r[-1].strip():
                continue
            try:
                v = float(r[-1])
            except ValueError:
                continue
            r[-1] = ('%.*f' % (a.dec, v))
            cnt += 1
        with open(p, 'w', encoding='utf-8', newline='') as f:
            csv.writer(f).writerows(rows)
        print('%s: 末列(%s) 已四舍五入到 %d 位，%d 格' % (k, last, a.dec, cnt))
if __name__ == '__main__':
    main()
