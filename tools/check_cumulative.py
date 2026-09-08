# -*- coding: utf-8 -*-
"""检查各题材数据是不是「年初至今累计」口径。

判据：同一年内把各期排成时间序列，
  · 季度：Q1→Q2→Q3→Q4 单调递增的比例
  · 月度：M01→…→M12 单调递增的比例
累计口径（利润表/现金流量表原始值）会接近 100%，
单季口径（已差分）或时点数（资产负债表）会接近随机（~10-30%）。

用法：python scripts_local/check_cumulative.py
"""
import csv
import glob
import os
import re
from collections import defaultdict

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(WS)

QRE = re.compile(r'^(\d{4})Q([1-4])$')
YRE = re.compile(r'^(\d{4})$')
MRE = re.compile(r'^(\d{4})[-/](0[1-9]|1[0-2])$')


def to_f(x):
    if x is None:
        return None
    s = str(x).strip().replace(',', '')
    if s in ('', '-', '—', 'na', 'NA', 'None', 'nan'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load(path):
    with open(path, encoding='utf-8-sig') as f:
        rd = csv.reader(f)
        rows = list(rd)
    if not rows:
        return None
    head = rows[0]
    cols = head[1:]
    data = {}
    for r in rows[1:]:
        if not r:
            continue
        name = r[0].strip()
        data[name] = [to_f(v) for v in r[1:len(cols) + 1]]
    return cols, data


def classify(cols):
    q = sum(1 for c in cols if QRE.match(c))
    m = sum(1 for c in cols if MRE.match(c))
    y = sum(1 for c in cols if YRE.match(c))
    if q > m and q > y:
        return 'quarter', q
    if m > q and m > y:
        return 'month', m
    return 'year', y


def analyze(path):
    got = load(path)
    if not got:
        return None
    cols, data = got
    kind, n = classify(cols)
    if kind == 'year':
        return {'kind': 'year', 'n': n, 'ratio': None, 'samples': 0}

    # 按年分组
    groups = defaultdict(list)   # year -> [(idx_in_year, col_idx)]
    for i, c in enumerate(cols):
        if kind == 'quarter':
            m = QRE.match(c)
            if m:
                groups[m.group(1)].append((int(m.group(2)) - 1, i))
        else:
            m = MRE.match(c)
            if m:
                groups[m.group(1)].append((int(m.group(2)) - 1, i))

    up = tot = 0
    # 断崖检测：累计口径下 Q4（全年累计）→ 次年 Q1（重新起算）会系统性跌到约 1/4；
    # 单季口径下 Q4 → 次年 Q1 比值中位数应接近 1。
    drop = []
    years = sorted(groups.keys())
    for y, idxs in groups.items():
        idxs.sort()
        need = 4 if kind == 'quarter' else 12
        if len(idxs) < need:
            continue
        seq_idx = [i for _, i in idxs]
        for name, vals in data.items():
            seq = [vals[i] for i in seq_idx]
            if any(v is None for v in seq):
                continue
            # 全 0 / 全等的行没有信息量，会计成「递增」污染统计，跳过
            if len(set(seq)) <= 1:
                continue
            tot += 1
            if all(seq[i] <= seq[i + 1] for i in range(len(seq) - 1)):
                up += 1
            # 跨年断崖：本年最后一期 vs 次年第一期
            ny = str(int(y) + 1)
            if ny in groups and len(groups[ny]) >= need:
                nxt = sorted(groups[ny])[0][1]
                last = seq_idx[-1]
                a, b = vals[last], vals[nxt]
                if a and b and a > 0 and b > 0:
                    drop.append(b / a)
    ratio = (up / tot) if tot else None
    drop_med = None
    if drop:
        drop.sort()
        drop_med = drop[len(drop) // 2]
    return {'kind': kind, 'n': n, 'ratio': ratio, 'samples': tot, 'drop': drop_med}


def main():
    files = sorted(glob.glob('data/topics_csv/*.csv'))
    rows = []
    for f in files:
        try:
            r = analyze(f)
        except Exception as e:
            print('跳过 %s: %s' % (f, e))
            continue
        if not r:
            continue
        rows.append((os.path.basename(f), r))

    def verdict(r):
        if r['kind'] == 'year':
            return '年度值'
        if r['ratio'] is None:
            return '—'
        # 断崖比 ~0.25 → 累计；~1.0 → 单季
        d = r.get('drop')
        if d is not None and d < 0.45:
            return '⚠️ 累计口径'
        if r['ratio'] >= 0.80:
            return '⚠️ 疑似累计'
        if r['ratio'] >= 0.55:
            return '❓ 偏高'
        return '✅ 非累计'

    print('%-38s %-8s %-5s %-6s %-8s %s' % ('数据文件', '粒度', '列数', '递增%', '跨年比', '判定'))
    print('-' * 92)
    for name, r in sorted(rows, key=lambda x: (x[1].get('drop') if x[1].get('drop') is not None else 9,
                                               -(x[1]['ratio'] or -1))):
        ra = r['ratio']
        d = r.get('drop')
        print('%-38s %-8s %-5d %-6s %-8s %s' % (
            name, r['kind'], r['n'],
            ('%.0f%%' % (ra * 100)) if ra is not None else '—',
            ('%.2f' % d) if d is not None else '—',
            verdict(r)))


if __name__ == '__main__':
    main()
