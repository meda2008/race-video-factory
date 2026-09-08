# -*- coding: utf-8 -*-
"""WDI 数据集「延展刷新」：保留原 CSV 实体集合，只追加 > 原末年的新年份列。
自动从「原 CSV 与 WDI 原始值重叠年份」推导单位换算系数(scale)与小数位(decimals)，
因此无需为每个题材手工配置单位（外汇储备亿美元、专利件数等都能自适应）。
用法：python refresh_wdi_extend.py <key> <indicator> [--start 1960]
"""
import argparse, csv, os, re, sys, glob, json
import urllib.request, ssl
from io import StringIO

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(WS, 'scripts_local'))
import fetch_owid as FO
try:
    import entity_cn      # 实体名中文化（2026-09-06 起 CSV 首列统一中文）
except Exception:                                     # noqa: BLE001
    entity_cn = None

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE

# WDI 英文国名 -> OWID 英文（再经 FO.CN 转中文）；覆盖 WDI 的非常规命名
ALIAS = {
    'Korea, Rep.': 'South Korea', "Korea, Dem. People's Rep.": 'North Korea',
    'Egypt, Arab Rep.': 'Egypt', 'Iran, Islamic Rep.': 'Iran',
    'Venezuela, RB': 'Venezuela', 'Yemen, Rep.': 'Yemen',
    'Gambia, The': 'Gambia', 'Bahamas, The': 'Bahamas',
    'Kyrgyz Republic': 'Kyrgyzstan', 'Lao PDR': 'Laos',
    'Russian Federation': 'Russia', 'Vietnam': 'Vietnam',
    'Egypt, Arab Rep.': 'Egypt', 'Hong Kong SAR, China': 'Hong Kong',
    'Taiwan': 'Taiwan', 'Korea': 'South Korea',
    'United States': 'United States', 'China': 'China',
}
REV = {}
for eng, cn in FO.CN.items():
    REV[FO._norm(eng)] = cn
for eng, cn in FO.CN.items():
    REV[FO._norm(eng)] = cn

def norm(s):
    return FO._norm(s)

def wdi_name_to_cn(wdi_name):
    n = norm(wdi_name)
    if n in ALIAS:
        n2 = norm(ALIAS[wdi_name])
        if n2 in REV:
            return REV[n2]
    if n in REV:
        return REV[n]
    return None

def resolve_csv(key, param_path):
    cands = []
    if param_path:
        cands.append(os.path.join(WS, param_path))
    cands.append(os.path.join(WS, 'data', 'topics_csv', key + '.csv'))
    cands.append(os.path.join(WS, 'topics', key + '.csv'))
    for c in cands:
        if os.path.exists(c):
            return c
    hits = glob.glob(os.path.join(WS, '**', key + '.csv'), recursive=True)
    return hits[0] if hits else None

def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f))
    years = [y for y in rows[0][1:] if y.strip()]
    data, names = {}, []
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        n = r[0].strip(); names.append(n)
        data[n] = {y: (r[i + 1].strip() if i + 1 < len(r) else '') for i, y in enumerate(years)}
    return names, years, data

def fetch_wdi(indicator, start, end):
    url = ('https://api.worldbank.org/v2/country/all/indicator/%s'
           '?format=json&per_page=20000&date=%d:%d' % (indicator, start, end))
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
        meta = json.loads(r.read().decode('utf-8'))
    series_cn = {}   # 中文名 -> {year: raw}
    series_en = {}   # 归一化英文名 -> {year: raw}
    for row in (meta[1] or []):
        if not row or row.get('value') is None:
            continue
        en = row['country']['value']
        raw = row['value']
        series_en.setdefault(norm(en), {})[str(row['date'])] = raw
        cn = wdi_name_to_cn(en)
        if cn:
            series_cn.setdefault(cn, {})[str(row['date'])] = raw
    return series_cn, series_en

# 中文名 -> 英文名（FO.CN 反查），用于把中文实体映射到 WDI 英文
CN_TO_EN = {v: k for k, v in FO.CN.items()}
# 特殊中文名别名
ALIAS_CN = {'全国总人口': 'China', '中国大陆': 'China', '中国（大陆）': 'China',
            '中国台湾': 'Taiwan', '中国香港': 'Hong Kong', '中国澳门': 'Macao'}

def lookup_series(name, series_cn, series_en):
    """按现有 CSV 的命名习惯（中文或英文）定位 WDI 序列。"""
    if re.search(r'[一-鿿]', name):
        if name in ALIAS_CN:
            return series_en.get(norm(ALIAS_CN[name]))
        en = CN_TO_EN.get(name)
        if en:
            return series_en.get(norm(en))
        return series_cn.get(name)
    return series_en.get(norm(name))

def en_keys(name):
    """CSV 里的中文实体名 -> 上游候选英文名列表（含原名自身，逐个尝试）。"""
    out = [name]
    if entity_cn is not None and re.search(r'[一-鿿]', str(name)):
        for en in entity_cn.en_candidates(name):
            if en not in out:
                out.append(en)
    return out


def find_series(name, series_cn, series_en):
    """按 CSV 现有命名（中文或英文）定位 WDI 序列，中文名会反查全部英文候选。"""
    for k in en_keys(name):
        s = lookup_series(k, series_cn, series_en)
        if s:
            return s
    return None


def coverage_gate(new_years, names, years, data, getval, ratio=0.8, floor=0.35):
    """覆盖率护栏（2026-09-06 加）：新年份列的有效实体占比不能相对前一年塌陷。

    背景：WDI/OWID 的「最新一年」往往只有少数国家上报，直接追加会让竞速视频末帧
    大面积掉柱。规则：逐年接受，一旦某年覆盖率 < max(floor, 前一年覆盖率*ratio)
    就丢弃该年及其之后所有年份。
    """
    def cov_prev(y):
        c = sum(1 for n in names if (data[n].get(str(y)) or '').strip())
        return c / max(1, len(names))

    def cov_new(y):
        c = sum(1 for n in names if getval(n, str(y)) is not None)
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
    ap.add_argument('key'); ap.add_argument('indicator')
    ap.add_argument('--start', type=int, default=1960)
    ap.add_argument('--end', type=int, default=2030)
    a = ap.parse_args()

    path = resolve_csv(a.key, None)
    if not path:
        sys.exit('找不到 %s 的 CSV' % a.key)
    names, years, data = read_csv(path)
    last = max(int(y) for y in years if str(y).isdigit())
    print('[%s] %s 原末年=%s，实体 %d 个' % (a.key, path, last, len(names)))

    series_cn, series_en = fetch_wdi(a.indicator, a.start, a.end)
    # 新年份（取 WDI 实际最大年，但只追加 > last 的）
    allv = [v for v in series_cn.values()] + [v for v in series_en.values()]
    wdi_max = max((max(int(y) for y in v) for v in allv if v), default=last)
    new_years = [y for y in range(last + 1, wdi_max + 1)]
    if not new_years:
        print('  WDI 最大年=%s，无更新年份，跳过' % wdi_max)
        return
    print('  WDI 实际最大年=%s，候选追加 %s~%s' % (wdi_max, new_years[0], new_years[-1]))

    def _getval(n, y):
        s = find_series(n, series_cn, series_en)
        if not s:
            return None
        raw = s.get(str(y))
        return raw if raw is not None else None

    new_years = coverage_gate(new_years, names, years, data, _getval)
    if not new_years:
        print('  覆盖率护栏未通过，放弃追加')
        return

    # 自动推导 scale + decimals：用重叠年份(实体,年)配对
    scales = []
    dec_set = set()
    for n in names:
        s = find_series(n, series_cn, series_en)
        for y, sval in data[n].items():
            if not sval:
                continue
            try:
                fv = float(sval)
            except ValueError:
                continue
            d = sval.split('.')
            if len(d) == 2:
                dec_set.add(len(d[1]))
            raw = s.get(y) if s else None
            if raw and raw != 0:
                scales.append(fv / raw)
    if not scales:
        sys.exit('ERROR: 原 CSV 与 WDI 无重叠可对齐的数值，无法推导单位，已放弃写入。')
    scales.sort()
    scale = scales[len(scales) // 2]
    decimals = min(max(dec_set) if dec_set else 2, 4)
    print('  推导 scale=%.6g  小数位=%d  (基于 %d 个重叠配对)' % (scale, decimals, len(scales)))

    out_years = list(years) + [str(y) for y in new_years]
    added = 0
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['name'] + out_years)
        for n in names:
            row = [data[n].get(y, '') for y in years]
            s = find_series(n, series_cn, series_en)
            for y in new_years:
                raw = s.get(str(y)) if s else None
                if raw is None:
                    row.append('')
                else:
                    row.append('%.*f' % (decimals, raw * scale))
                    added += 1
            w.writerow([n] + row)
    print('  写出 %s：%d 实体 × %d 列，新单元格 %d 个' % (path, len(names), len(out_years), added))

if __name__ == '__main__':
    main()
