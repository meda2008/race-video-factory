# -*- coding: utf-8 -*-
"""OWID 数据集「延展刷新」：保留原 CSV 的实体集合，只追加 > 原末年 的新年份列。

与 fetch_owid.py 的区别：不改写实体（避免竞速画面大变样），只把数据延长到最新。
用法：python refresh_owid_extend.py <key> <slug> [--end 2025]
需要 requests/pandas（managed venv）。
"""
import argparse, csv, os, re, sys, json, glob
from io import StringIO
import pandas as pd
import requests

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 复用 fetch_owid 的 CN 映射与 MICRO 名单
sys.path.insert(0, os.path.join(WS, 'scripts_local'))
import fetch_owid as FO
try:
    import entity_cn      # 实体名中文化（2026-09-06 起 CSV 首列统一中文）
except Exception:                                     # noqa: BLE001
    entity_cn = None

H = FO.H

def resolve_csv(key, param_path):
    cands = []
    if param_path:
        cands.append(os.path.join(WS, param_path))
    cands.append(os.path.join(WS, 'data', 'topics_csv', key + '.csv'))
    cands.append(os.path.join(WS, 'topics', key + '.csv'))
    if param_path:
        cands.append(os.path.join(WS, 'topics', os.path.basename(param_path)))
    for c in cands:
        if os.path.exists(c):
            return c
    hits = glob.glob(os.path.join(WS, '**', key + '.csv'), recursive=True)
    return hits[0] if hits else None

def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f))
    years = [y for y in rows[0][1:] if y.strip()]
    data = {}
    names = []
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        n = r[0].strip()
        names.append(n)
        data[n] = {y: (r[i + 1].strip() if i + 1 < len(r) else '') for i, y in enumerate(years)}
    return names, years, data

def fetch_panel(slug, end):
    url = f'https://ourworldindata.org/grapher/{slug}.csv?v=1&csvType=full'
    r = requests.get(url, headers=H, timeout=120)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    cols = list(df.columns)
    vcol = [c for c in cols if c not in ('Entity', 'Code', 'Year')][0]
    df = df[df['Code'].notna() & df['Code'].astype(str).str.fullmatch(r'[A-Z]{3}')]
    micro_norm = {FO._norm(x) for x in FO.MICRO}
    df = df[~df['Entity'].map(lambda e: FO._norm(e) in micro_norm)]
    df = df[df['Year'] <= end]
    panel = {}
    ENT_IDX.clear()                       # 归一化英文名 -> panel 键
    for _, row in df.iterrows():
        ent = row['Entity']
        if entity_cn is not None:
            cn = entity_cn.cn_name(ent)   # 统一中文名，与 CSV 首列口径一致
        else:
            cn = FO.CN.get(ent, FO.CN.get(ent.strip(), ent))
        panel.setdefault(cn, {})[int(row['Year'])] = row[vcol]
        ENT_IDX.setdefault(FO._norm(ent), cn)
        ENT_IDX.setdefault(FO._norm(cn), cn)
    return panel, vcol


# fetch_panel 每次重建；find_panel 只读
ENT_IDX = {}


def find_panel(n, panel):
    """按 CSV 现有命名定位 OWID 序列。

    三级兜底：① 原名直接命中 ② 归一化索引（中英皆可）
              ③ 中文名反查英文候选（含 FO.CN 口径）
    2026-09-06 注：CSV 首列统一中文化后，① 的命中率从 25% 升到 95%
    （旧流程 CSV 是英文、panel 键是 FO.CN 中文，两边口径不一致导致大国反而漏配）。
    """
    if n in panel:
        return panel[n]
    k = FO._norm(n)
    if k in ENT_IDX and ENT_IDX[k] in panel:
        return panel[ENT_IDX[k]]
    if entity_cn is not None:
        for en in entity_cn.en_candidates(n):
            for cand in (en, FO.CN.get(en, FO.CN.get(en.strip(), en))):
                k2 = FO._norm(cand)
                if k2 in ENT_IDX and ENT_IDX[k2] in panel:
                    return panel[ENT_IDX[k2]]
    return None

def coverage_gate(new_years, names, years, data, getval, ratio=0.8, floor=0.35):
    """覆盖率护栏（2026-09-06 加）：新年份列的有效实体占比不能相对前一年塌陷。

    背景：OWID 的「最新一年」常常只有少数国家上报，直接追加会让竞速视频末帧大面积
    掉柱。规则：逐年接受，一旦某年覆盖率 < max(floor, 前一年覆盖率*ratio) 就丢弃
    该年及其之后所有年份。
    """
    def cov_prev(y):
        c = sum(1 for n in names if (data[n].get(str(y)) or '').strip())
        return c / max(1, len(names))

    def cov_new(y):
        c = 0
        for n in names:
            v = getval(n, int(y))
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                c += 1
        return c / max(1, len(names))

    prev = cov_prev(years[-1])
    keep = []
    for y in new_years:
        c = cov_new(y)
        need = max(floor, prev * ratio)
        if c < need:
            print('  ⛔ %s 覆盖率 %.0f%% < 门槛 %.0f%%（前一年 %.0f%%）→ 丢弃该年及之后'
                  % (y, c * 100, need * 100, prev * 100))
            break
        print('  ✓ %s 覆盖率 %.0f%%（前一年 %.0f%%）' % (y, c * 100, prev * 100))
        keep.append(y)
        prev = c
    return keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('key'); ap.add_argument('slug')
    ap.add_argument('--end', type=int, default=2025)
    a = ap.parse_args()

    path = resolve_csv(a.key, None)
    if not path:
        sys.exit('找不到 %s 的 CSV' % a.key)
    names, years, data = read_csv(path)
    last = max(int(y) for y in years if str(y).isdigit())
    print('[%s] %s 原末年=%s，实体 %d 个' % (a.key, path, last, len(names)))

    panel, vcol = fetch_panel(a.slug, a.end)
    # 新年份
    new_years = [y for y in sorted({y for v in panel.values() for y in v}) if y > last]
    if not new_years:
        print('  OWID 无更新年份（末年已是 %s），跳过' % last)
        return
    print('  候选追加年份: %s~%s' % (new_years[0], new_years[-1]))

    def _getval(n, y):
        p = find_panel(n, panel)
        return p.get(y) if p else None

    new_years = coverage_gate(new_years, names, years, data, _getval)
    if not new_years:
        print('  覆盖率护栏未通过，放弃追加')
        return

    print('  实际追加年份: %s~%s' % (new_years[0], new_years[-1]))

    matched = 0
    all_years = [str(y) for y in range(int(years[0]) if str(years[0]).isdigit() else last, new_years[-1] + 1)]
    # 重构列：保留原列 + 新列
    orig_years = [y for y in years]
    out_years = orig_years + [str(y) for y in new_years]
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['name'] + out_years)
        for n in names:
            row = []
            for y in orig_years:
                row.append(data[n].get(y, ''))
            pw = find_panel(n, panel) or {}
            for y in new_years:
                val = pw.get(y)
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    row.append('')
                else:
                    row.append(f'{val:g}')
                    matched += 1
            w.writerow([n] + row)
    print('  写出 %s：%d 实体 × %d 列，新单元格 %d 个' % (path, len(names), len(out_years), matched))

if __name__ == '__main__':
    main()
