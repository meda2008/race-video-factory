#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""WDI 取数器（最新版本）：自动探测「实际最新可用年份」，把数据更新到最新时间。

背景：此前各题材 CSV 的末年都是取数脚本里硬编码的，导致数据滞后
      （如 m2_gdp 只到 2023，而 WDI 实际已发布到 2025）。
本脚本把「末年」改为**运行时向 API 探测**，任何指标都能自动取到最新。

用法（Bash 里务必用 C:/ 形式路径，勿用 /c/Users/...）：
  C:/Users/medam/.workbuddy/binaries/python/envs/default/Scripts/python.exe \
      C:/Users/medam/WorkBuddy/视频测试/batch2_ws/fetch_wdi_latest.py m2_gdp

输出：覆盖写入对应的 data/topics_csv/*.csv（宽表：name,年,年,...）

铁律：只写入 API 真实返回的数值；某国某年无数据则留空，**绝不插值/估算/编造**。
"""
import csv
import json
import sys
import time
import urllib.request

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
CSV_DIR = 'C:/Users/medam/WorkBuddy/视频测试/batch2_ws/data/topics_csv/'

# 题材配置：indicator=WDI 指标码，countries=中文名→WDI 两字母码，start=起始年
TOPICS = {
    'm2_gdp': {
        'csv': 'm2_gdp.csv',
        'indicator': 'FM.LBL.BMNY.GD.ZS',   # 广义货币占GDP比重(%)
        'start': 2010,
        'decimals': 2,
        'scale': 1.0,
        # 覆盖率阈值：本片涉及的实体中至少 70% 该年有真实数据，才把该年作为末年。
        # 2025 年 WDI 仅 9/22 国发布（缺中国/英国/韩国等），末帧会大面积掉柱，故会被自动跳过。
        'min_coverage': 0.7,
        'countries': {
            '美国': 'US', '中国': 'CN', '日本': 'JP', '英国': 'GB', '印度': 'IN',
            '巴西': 'BR', '韩国': 'KR', '俄罗斯': 'RU', '南非': 'ZA', '印尼': 'ID',
            '墨西哥': 'MX', '澳大利亚': 'AU', '瑞士': 'CH', '沙特阿拉伯': 'SA',
            '土耳其': 'TR', '瑞典': 'SE', '波兰': 'PL', '挪威': 'NO',
            '阿联酋': 'AE', '泰国': 'TH', '马来西亚': 'MY', '新加坡': 'SG',
        },
    },
    'stock_mcap': {
        'csv': 'stock_mcap.csv',
        'indicator': 'CM.MKT.LCAP.CD',      # 股市总市值(现价美元)
        'start': 1995,
        'decimals': 2,
        'scale': 1e-12,                     # 万亿美元
        'min_coverage': 0.5,                # 该指标本身缺年较多（末年 22/30），阈值放宽
        'countries': {
            '美国': 'US', '中国': 'CN', '日本': 'JP', '德国': 'DE', '英国': 'GB',
            '法国': 'FR', '印度': 'IN', '加拿大': 'CA', '巴西': 'BR', '韩国': 'KR',
            '俄罗斯': 'RU', '南非': 'ZA', '印尼': 'ID', '墨西哥': 'MX',
            '澳大利亚': 'AU', '西班牙': 'ES', '意大利': 'IT', '瑞士': 'CH',
            '荷兰': 'NL', '沙特阿拉伯': 'SA', '土耳其': 'TR', '瑞典': 'SE',
            '波兰': 'PL', '挪威': 'NO', '比利时': 'BE', '奥地利': 'AT',
            '阿联酋': 'AE', '泰国': 'TH', '马来西亚': 'MY', '新加坡': 'SG',
        },
    },
    'gdp_per_capita': {
        'csv': 'gdp_per_capita.csv',
        'indicator': 'NY.GDP.PCAP.CD',      # 人均GDP(现价美元)
        'start': 1990,
        'decimals': 2,
        'scale': 1.0,
        'min_coverage': 0.7,
        'countries': {
            '美国': 'US', '中国': 'CN', '日本': 'JP', '德国': 'DE', '英国': 'GB',
            '法国': 'FR', '印度': 'IN', '加拿大': 'CA', '巴西': 'BR', '韩国': 'KR',
            '俄罗斯': 'RU', '南非': 'ZA', '印尼': 'ID', '墨西哥': 'MX',
            '澳大利亚': 'AU', '西班牙': 'ES', '意大利': 'IT', '瑞士': 'CH',
            '荷兰': 'NL', '沙特阿拉伯': 'SA', '土耳其': 'TR', '瑞典': 'SE',
            '波兰': 'PL', '挪威': 'NO', '比利时': 'BE', '奥地利': 'AT',
            '阿联酋': 'AE', '泰国': 'TH', '马来西亚': 'MY', '新加坡': 'SG',
            '卢森堡': 'LU',
        },
    },
}


def api_get(url, retries=3):
    """带重试的 GET。

    为什么必须重试：观测到 WDI 接口会偶发 `SSL: UNEXPECTED_EOF_WHILE_READING`
    等传输层错误。若不加区分地让异常冒出去、或静默当「无数据」处理，
    都会被下游误判为「该年确实没数据」，进而触发覆盖率回退甚至清表（已有事故）。
    故：连续失败才判定为取数失败，由调用方中止且不写盘。
    """
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:  # noqa: BLE001 - 网络层异常类型多，统一重试后上抛
            last = e
            if i < retries - 1:
                time.sleep(2 * (i + 1))
                continue
    raise RuntimeError('WDI 请求连续 %d 次失败（网络/SSL/限流）：%s' % (retries, last))


def probe_latest_year(indicator, probe_from=2020):
    """探测该指标实际最新有数据的年份（不再硬编码末年）。"""
    url = ('https://api.worldbank.org/v2/country/all/indicator/%s'
           '?format=json&per_page=20000&date=%d:2030' % (indicator, probe_from))
    meta = api_get(url)
    years = set()
    for row in (meta[1] or []):
        if row and row.get('value') is not None:
            years.add(str(row['date']))
    return max(int(y) for y in years) if years else None


def pick_usable_year(series, cmap, names, start, latest, threshold):
    """在 start~latest 里选「覆盖率达标的最新年」，而不是无脑取最大年。

    为什么需要这一步：WDI 最新年份常只有少数经济体已发布（如 m2_gdp 的 2025
    仅 9/22 国有值），若直接取最大年，竞速的**最后一帧会大面积掉柱**——
    中国等高亮主体直接消失，高潮帧崩掉。故改为：从最新年往回找，
    返回 (年份 or None, 各年覆盖率报告)。**没有任何年份达标时返回 None**——
    由调用方决定中止，绝不退回 start（那会让 CSV 塌成 1 列、整表数据被清空）。
    这既满足「尽量取最新」，又保证成片观感与数据完整性。
    """
    report = []
    for y in range(latest, start - 1, -1):
        have = sum(1 for n in names
                   if cmap.get(n) and series.get(cmap[n], {}).get(str(y)) is not None)
        cov = have / len(names) if names else 0
        report.append((y, have, cov))
        if cov >= threshold:
            return y, report
    return None, report


def fetch_series(indicator, codes, start, end):
    """返回 {两字母码: {年份字符串: 原始值}}。注意 date 字段是字符串。"""
    out = {}
    chunk = 20
    for i in range(0, len(codes), chunk):
        grp = ';'.join(codes[i:i + chunk])
        url = ('https://api.worldbank.org/v2/country/%s/indicator/%s'
               '?format=json&per_page=20000&date=%d:%d' % (grp, indicator, start, end))
        meta = api_get(url)
        for row in (meta[1] or []):
            if not row or row.get('value') is None:
                continue
            cid = row['country']['id']
            out.setdefault(cid, {})[str(row['date'])] = row['value']
    return out


def read_existing(path):
    """读现有 CSV，返回 (实体中文名列表, {名: {年: 原字符串}})"""
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], {}
    years = rows[0][1:]
    data = {}
    names = []
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        n = r[0].strip()
        names.append(n)
        data[n] = {y: (r[i + 1].strip() if i + 1 < len(r) else '')
                   for i, y in enumerate(years)}
    return names, data


def main():
    key = sys.argv[1] if len(sys.argv) > 1 else 'm2_gdp'
    cfg = TOPICS[key]
    path = CSV_DIR + cfg['csv']

    # 探测与取数都可能因网络/SSL/限流失败；失败必须明确中止，绝不带空数据往下走。
    try:
        latest = probe_latest_year(cfg['indicator'])
    except RuntimeError as e:
        sys.exit('ERROR: 探测最新年份失败：%s\n  已放弃，%s 未被改动。' % (e, path))
    print('[%s] %s 实际最新可用年份 -> %s（CSV 原末年需对比）'
          % (key, cfg['indicator'], latest))
    if not latest:
        sys.exit('探测不到任何数据')

    names, existing = read_existing(path)
    # 国家码映射：优先用配置，未配置则留空（由调用方补齐）
    cmap = cfg['countries']
    codes = [cmap[n] for n in names if n in cmap]
    missing = [n for n in names if n not in cmap]
    if missing:
        print('  警告：以下实体未配置国家码，将沿用原值：%s' % '、'.join(missing))

    start, latest = cfg['start'], latest
    try:
        series = fetch_series(cfg['indicator'], codes, start, latest)
    except RuntimeError as e:
        sys.exit('ERROR: 取数失败：%s\n  已放弃写入，%s 保持原样未被破坏。' % (e, path))
    rev = {v: k for k, v in cmap.items()}

    # 【护栏 1】取数为空 -> 中止，绝不覆盖。
    # 曾发生事故：API 未返回任何数据（指标码/网络/限流）时，脚本仍继续写盘，
    # 把 30 国×31 年的 stock_mcap.csv 清成只剩 1995 一列。宁可不动，也不能毁数据。
    if not series or sum(len(v) for v in series.values()) == 0:
        sys.exit('ERROR: API 未返回任何数据（指标码错？网络/限流？）。\n'
                 '  已放弃写入，%s 保持原样未被破坏。\n'
                 '  请检查 indicator=%s 与网络后重试。' % (path, cfg['indicator']))

    # 自动选取「覆盖率达标的最新年」：避免最新年只有少数经济体发布导致成片末帧掉柱
    thr = cfg.get('min_coverage', 0.7)
    end, report = pick_usable_year(series, cmap, names, start, latest, thr)

    # 【护栏 2】没有任何年份达到覆盖率阈值 -> 同样中止，不写盘。
    if end is None:
        print('  覆盖率把关：start~%d 内没有任何年份达到阈值 %.0f%%' % (latest, thr * 100))
        for y, have, cov in report[:4]:
            print('      %d 年: %d/%d 国有值 (%.0f%%)' % (y, have, len(names), cov * 100))
        sys.exit('ERROR: 无可用年份，已放弃写入，%s 保持原样未被破坏。'
                 '可调低该题材的 min_coverage 或检查取数。' % path)

    if end != latest:
        print('  覆盖率把关：最新年 %d 覆盖不足（阈值 %.0f%%），回退末年 -> %d'
              % (latest, thr * 100, end))
        for y, have, cov in report[:4]:
            print('      %d 年: %d/%d 国有值 (%.0f%%)%s'
                  % (y, have, len(names), cov * 100,
                     ' <- 采用' if y == end else ''))
    else:
        print('  采用最新年 %d（覆盖率达标）' % end)

    # 【护栏 3】年份区间只许延长、不许缩短：
    # 原 CSV 的末年若比本次算出的 end 更晚，必须保留（否则刷新会把历史列静默删掉）。
    orig_years = []
    for row in existing.values():
        for y in row:
            if str(y).isdigit():
                orig_years.append(int(y))
    orig_last = max(orig_years) if orig_years else end
    end_out = max(end, orig_last)
    if end_out != end:
        print('  保留原 CSV 已存在的年份：末年 %d -> %d（刷新只延长、不截断）'
              % (end, end_out))
    years = [str(y) for y in range(start, end_out + 1)]
    scale = cfg['scale']
    dec = cfg['decimals']
    added = 0
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['name'] + years)
        for n in names:
            code = cmap.get(n)
            row = []
            for y in years:
                raw = None
                if code and code in series:
                    raw = series[code].get(y)
                if raw is None:
                    # API 无数据 -> 沿用原 CSV 值（可能为空）
                    row.append(existing.get(n, {}).get(y, ''))
                else:
                    if y not in existing.get(n, {}):
                        added += 1
                    row.append('%.*f' % (dec, raw * scale))
            w.writerow([n] + row)
    print('  已写入 %s：年份 %s~%s（%d 列），新增/刷新单元格 %d 个'
          % (path, years[0], years[-1], len(years), added))
    print('  注：API 无数据的单元格沿用原值（多为留空），未做任何插值/估算。')


if __name__ == '__main__':
    main()
