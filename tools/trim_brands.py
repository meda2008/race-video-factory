# -*- coding: utf-8 -*-
"""裁剪 brands.csv：只保留「任意一年进入 Top N」的品牌。

原因：build_race 的 ROW_H = max(34, 1180/实体数)，实体过多时后面的行被挤出画布，
渲染 157 行纯属浪费。裁剪到 30 行左右，行高约 39px，字体可读且竞速有看头。
"""
import csv
import os
import sys

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(WS, 'data', 'topics_csv', 'brands.csv')
DST = os.path.join(WS, 'data', 'topics_csv', 'brands_top.csv')
TOP_N = int(sys.argv[1]) if len(sys.argv) > 1 else 25


def main():
    rows = list(csv.reader(open(SRC, encoding='utf-8-sig')))
    hdr = rows[0]
    years = hdr[1:]
    data = {}
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        vals = {}
        ok = False
        for i, y in enumerate(years):
            raw = r[i + 1].strip() if i + 1 < len(r) else ''
            v = float(raw) if raw else 0.0
            vals[y] = v
            if v > 0:
                ok = True
        if ok:
            data[r[0].strip()] = vals

    keep = set()
    for y in years:
        ranked = sorted(data.items(), key=lambda kv: kv[1].get(y, 0.0), reverse=True)
        for name, _ in ranked[:TOP_N]:
            if data[name].get(y, 0.0) > 0:
                keep.add(name)

    print(f'原 {len(data)} 品牌 -> 保留 {len(keep)}（任意年份 Top{TOP_N}）')

    # 按末年值降序输出，保证首帧顺序稳定
    last = years[-1]
    order = sorted(keep, key=lambda n: data[n].get(last, 0.0), reverse=True)
    with open(DST, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['name'] + years)
        for n in order:
            w.writerow([n] + [f'{data[n].get(y, 0.0):g}' for y in years])
    print(f'写出 {DST}')
    print('末年 Top10:', [(n, data[n].get(last)) for n in order[:10]])


if __name__ == '__main__':
    main()
