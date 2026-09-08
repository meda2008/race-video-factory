# -*- coding: utf-8 -*-
"""亏损榜数据整形：盈利年份置空，亏损年份取绝对值。

为什么必须做这一步：
  净利润原始数据里亏损是负数。亏损榜要表达的是「亏得最多的人排第一」，
  但如果直接把负数丢进竞速引擎，排序是「数值降序」，最大（最接近 0）的排第一——
  结果 2004 年「中国铝业以 61 亿元领跑」——那其实是它当年**盈利** 61 亿，
  整个叙事完全反了。

故统一口径：
  - 当年盈利（>=0）→ 置空，表示「该年未进入亏损榜」
  - 当年亏损（<0） → 取绝对值，柱长 = 亏损规模（亿元）

用法：python fix_loss_sign.py [csv_name] [loss|profit]
  loss   —— 亏损榜：盈利格置空，亏损格取绝对值
  profit —— 盈利榜：亏损格置空（当年不进盈利榜），盈利格原样保留
"""
import csv
import os
import sys

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DIR = os.path.join(WS, 'data', 'topics_csv')


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else 'ashare_loss'
    mode = sys.argv[2] if len(sys.argv) > 2 else 'loss'
    if mode not in ('loss', 'profit'):
        raise SystemExit('mode 必须是 loss 或 profit')
    path = os.path.join(CSV_DIR, f'{name}.csv')
    rows = list(csv.reader(open(path, encoding='utf-8-sig')))
    hdr, years = rows[0], rows[0][1:]

    out = []
    n_drop = n_keep = 0
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        vals = []
        for raw in r[1:]:
            raw = (raw or '').strip()
            if raw == '':
                vals.append('')
                continue
            v = float(raw)
            if mode == 'loss':
                # 亏损榜：盈利 -> 未上榜；亏损 -> 取绝对值（柱长=亏损规模）
                if v >= 0:
                    vals.append('')
                    n_drop += 1
                else:
                    vals.append(f'{abs(v):.2f}')
                    n_keep += 1
            else:
                # 盈利榜：亏损 -> 未上榜；盈利 -> 原样
                if v < 0:
                    vals.append('')
                    n_drop += 1
                else:
                    vals.append(f'{v:.2f}')
                    n_keep += 1
        if any(v != '' for v in vals):
            out.append([r[0]] + vals)

    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(hdr)
        w.writerows(out)

    verb = '亏损取绝对值' if mode == 'loss' else '盈利保留'
    drop_verb = '盈利置空' if mode == 'loss' else '亏损置空'
    print(f'{name} [{mode}]: {drop_verb} {n_drop} 格，{verb} {n_keep} 格，保留 {len(out)} 家')
    last = years[-1]
    items = [(r[0], float(r[-1])) for r in out if r[-1]]
    items.sort(key=lambda kv: -kv[1])
    print(f'{last} Top8:', [(n, round(v, 1)) for n, v in items[:8]])


if __name__ == '__main__':
    main()
