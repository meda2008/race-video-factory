# -*- coding: utf-8 -*-
"""通用裁剪：只保留「任意一年进入 Top N」的实体。

两个原因：
1. build_race 的 ROW_H = max(34, 1180/实体数)，超出画布的行看不见，渲染纯属浪费。
2. gen_finance_meta 的口播稿会取「后三名」写文案，实体过多会念出一堆常年垫底、
   观众毫无概念的小国，直接毁掉口播。

用法：python trim_top.py <csv_name> [TOP_N] [--out <name>]
"""
import csv
import os
import sys

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DIR = os.path.join(WS, 'data', 'topics_csv')


def main():
    name = sys.argv[1]
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    out = None
    if '--out' in sys.argv:
        out = sys.argv[sys.argv.index('--out') + 1]
    # 强制保留的实体（高亮主体排不进 Top N 时用它兜底，否则高亮行会被裁掉）
    force = []
    if '--keep' in sys.argv:
        force = [x.strip() for x in sys.argv[sys.argv.index('--keep') + 1].split(',') if x.strip()]

    src = os.path.join(CSV_DIR, f'{name}.csv')
    dst = os.path.join(CSV_DIR, f'{out or name}.csv')
    rows = list(csv.reader(open(src, encoding='utf-8-sig')))
    hdr = rows[0]
    years = hdr[1:]

    data = {}
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        vals = {}
        for i, y in enumerate(years):
            raw = r[i + 1].strip() if i + 1 < len(r) else ''
            vals[y] = float(raw) if raw else None
        if any(v is not None for v in vals.values()):
            data[r[0].strip()] = vals

    keep = set()
    for y in years:
        ranked = sorted(data.items(),
                        key=lambda kv: kv[1].get(y) if kv[1].get(y) is not None else -1,
                        reverse=True)
        for n, _ in ranked[:top_n]:
            if data[n].get(y) is not None:
                keep.add(n)
    for n in force:
        if n in data:
            keep.add(n)
        else:
            print(f'  [warn] --keep 指定的「{n}」不在数据中，已忽略')

    last = years[-1]
    order = sorted(keep,
                   key=lambda n: data[n].get(last) if data[n].get(last) is not None else -1,
                   reverse=True)
    with open(dst, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['name'] + years)
        for n in order:
            w.writerow([n] + [('' if data[n].get(y) is None else f'{data[n][y]:g}') for y in years])

    print(f'{name}: {len(data)} -> {len(keep)}（任意年份 Top{top_n}）-> {dst}')
    print('  末年 Top8:',
          [(n, round(data[n][last], 2) if data[n].get(last) is not None else None)
           for n in order[:8]])


if __name__ == '__main__':
    main()
