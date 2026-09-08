#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""数据新鲜度巡检 + 扩年覆盖率护栏。

背景（2026-08-31 batch3 的教训）：
  竞速视频要求数据「尽量到最新时间」，但「最新」不等于「最新发布的年份」——
  若某新年份只有少数实体有值（如 WDI 的 M2/GDP 指标 2025 年 22 国里只有 9 国有值、
  且中国缺失），盲目扩年会让面板有效样本从 17 掉到 9、并丢掉高光实体，
  排名视频直接崩掉。故扩年必须先过「覆盖率护栏」。

本脚本提供两件事：
  1) 巡检 registry 里所有 csv 题材，报告每个题材的末年、末年覆盖率、以及落后
     「最新完整年」几年 —— 落后即应刷新（退出码非 0，可作 CI/自动化门禁）。
  2) 覆盖率护栏评估：给定一份 CSV 与「候选扩年列」的取值，判断该年能否采纳。

用法：
  # 巡检（默认最新完整年 = 去年，可用 --latest-year 覆盖）
  python check_freshness.py --registry <reg.json> --workspace <ws>

  # 护栏评估：候选年的各实体取值写在 JSON 文件里 {"实体": 值 或 null}
  python check_freshness.py --csv <panel.csv> --candidate-year 2026 \
      --candidate-values cand.json [--min-ratio 0.8] [--must-have 中国,美国]

  # 单看一份 CSV 的各年覆盖率剖面
  python check_freshness.py --csv <panel.csv> --profile

只读取、不修改任何文件。
"""
import argparse
import datetime
import json
import os
import sys

try:
    import csv
except ImportError:  # pragma: no cover
    csv = None


def read_panel(path):
    """返回 (表头年份列表, {实体: {年: 原始字符串}})。BOM 安全。"""
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = [r for r in csv.reader(f) if r and r[0].strip()]
    if not rows:
        return [], {}
    header = [c.strip() for c in rows[0]]
    years = header[1:]
    panel = {}
    for r in rows[1:]:
        name = r[0].strip()
        vals = {}
        for i, y in enumerate(years):
            v = r[i + 1].strip() if len(r) > i + 1 else ''
            vals[y] = v
        panel[name] = vals
    return years, panel


def coverage(panel, year):
    """该年非空且非 0 的实体数（0 在竞速里等价于「未上榜」）。"""
    n = 0
    for name, vals in panel.items():
        raw = vals.get(year, '')
        if raw in ('', None):
            continue
        try:
            if float(raw) != 0:
                n += 1
        except ValueError:
            n += 1
    return n


def profile(years, panel):
    return [(y, coverage(panel, y)) for y in years]


def latest_complete_year(today=None):
    """年度面板的「最新完整年」：今年之前的一年。

    例：2026-08-31 时，2026 尚未走完，最新完整年 = 2025。
    """
    today = today or datetime.date.today()
    return today.year - 1


def check_registry(reg_path, ws, latest_year):
    with open(reg_path, encoding='utf-8') as f:
        reg = json.load(f)
    topics = reg if isinstance(reg, list) else reg.get('topics', reg)
    rows = []
    lagging = 0
    for t in topics:
        if not isinstance(t, dict):
            continue
        key = t.get('key')
        p = t.get('params', t)
        rel = p.get('path') or p.get('csv')
        if not rel:
            continue
        path = rel if os.path.isabs(rel) else os.path.join(ws, rel)
        if not os.path.exists(path):
            rows.append((key, '?', 0, 'CSV 缺失: %s' % path))
            lagging += 1
            continue
        years, panel = read_panel(path)
        if not years:
            rows.append((key, '?', 0, 'CSV 空'))
            lagging += 1
            continue
        last_y = years[-1]
        cov = coverage(panel, last_y)
        try:
            lag = int(latest_year) - int(last_y)
        except (TypeError, ValueError):
            lag = 0
        total = len(panel)
        if lag > 0:
            lagging += 1
        rows.append((key, last_y, cov, '落后 %d 年 (末年覆盖 %d/%d)' % (lag, cov, total)
                     if lag > 0 else '已是最新完整年 (末年覆盖 %d/%d)' % (cov, total)))
    return rows, lagging


def evaluate_candidate(csv_path, cand_year, cand_values, min_ratio, must_have):
    """覆盖率护栏：判断候选年能否采纳。返回 (可否采纳, 说明列表)。"""
    years, panel = read_panel(csv_path)
    if not years:
        return False, ['CSV 为空，无法评估']
    prev_year = years[-1]
    prev_cov = coverage(panel, prev_year)
    cand_cov = sum(1 for v in cand_values.values()
                   if v not in ('', None) and _as_float(v) not in (0.0, None))
    msgs = []
    ok = True
    ratio = (cand_cov / prev_cov) if prev_cov else 0.0
    msgs.append('候选年 %s 覆盖 %d / 上年(%s)覆盖 %d → 比率 %.0f%%'
                % (cand_year, cand_cov, prev_year, prev_cov, ratio * 100))
    if ratio < min_ratio:
        ok = False
        msgs.append('❌ 覆盖率 %.0f%% < 阈值 %.0f%%：扩年会显著削弱面板' % (ratio * 100, min_ratio * 100))
    missing_key = [k for k in must_have
                   if k in panel and (cand_values.get(k) in ('', None)
                                      or _as_float(cand_values.get(k)) in (0.0, None))]
    if must_have:
        if missing_key:
            ok = False
            msgs.append('❌ 关键实体在候选年缺失或为 0：%s' % '、'.join(missing_key))
        else:
            msgs.append('✅ 关键实体 %s 在候选年均有值' % '、'.join(must_have))
    if ok:
        msgs.append('✅ 通过护栏，可以扩到 %s' % cand_year)
    return ok, msgs


def _as_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--registry', help='题材注册表 JSON')
    ap.add_argument('--workspace', help='workspace 根目录（注册表里相对路径的基准）')
    ap.add_argument('--csv', help='单份面板 CSV')
    ap.add_argument('--profile', action='store_true', help='打印该 CSV 各年覆盖率剖面')
    ap.add_argument('--candidate-year', help='候选扩年年份（配合 --candidate-values）')
    ap.add_argument('--candidate-values', help='候选年取值 JSON：{"实体": 值 或 null}')
    ap.add_argument('--min-ratio', type=float, default=0.8,
                    help='候选年覆盖 / 上年覆盖 的最低比率，默认 0.8')
    ap.add_argument('--must-have', default='', help='必须有值的实体，逗号分隔（如 中国,美国）')
    ap.add_argument('--latest-year', type=int, default=None,
                    help='最新完整年（默认 = 去年）')
    a = ap.parse_args()

    latest = a.latest_year or latest_complete_year()

    if a.csv:
        years, panel = read_panel(a.csv)
        if a.profile or not a.candidate_year:
            print('%s  年份 %s → %s' % (os.path.basename(a.csv), years[0], years[-1]))
            for y, c in profile(years, panel):
                print('  %s  覆盖 %d/%d' % (y, c, len(panel)))
        if a.candidate_year:
            if not a.candidate_values:
                sys.exit('ERROR: --candidate-year 需要配合 --candidate-values')
            with open(a.candidate_values, encoding='utf-8') as f:
                cand = json.load(f)
            must = [m for m in a.must_have.split(',') if m.strip()]
            ok, msgs = evaluate_candidate(a.csv, a.candidate_year, cand, a.min_ratio, must)
            for m in msgs:
                print(m)
            sys.exit(0 if ok else 2)
        return

    if not a.registry:
        sys.exit('ERROR: 需 --registry（+--workspace）或 --csv')

    rows, lagging = check_registry(a.registry, a.workspace or '.', latest)
    print('数据新鲜度巡检（最新完整年基准 = %d，今天 %s）'
          % (latest, datetime.date.today().isoformat()))
    print('-' * 72)
    print('%-16s %-8s %s' % ('题材 key', '末年', '状态'))
    print('-' * 72)
    for key, last_y, cov, note in rows:
        print('%-16s %-8s %s' % (str(key), str(last_y), note))
    print('-' * 72)
    print('落后题材数：%d' % lagging)
    print('提示：落后 ≠ 立刻能补。扩年前必须过覆盖率护栏')
    print('  python check_freshness.py --csv <panel.csv> --candidate-year <年> \\')
    print('      --candidate-values cand.json --min-ratio 0.8 --must-have 中国')
    sys.exit(1 if lagging else 0)


if __name__ == '__main__':
    main()
