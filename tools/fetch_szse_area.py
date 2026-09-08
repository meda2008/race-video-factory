# -*- coding: utf-8 -*-
"""深交所「地区交易分布」月度取数 -> 宽表 CSV（地区 × 月份）。

ak.stock_szse_area_summary(date='YYYYMM')，实测 2004-12 是第一个有数月。
两个已知口径坑，必须处理：
1. 广东被拆成「广东 / 深圳 / 广州」三行（深圳、广州为计划单列统计口径），
   不合并的话「广东」排名会离谱地低。这里合并为「广东(含深穗)」并保留可核对说明。
2. 西藏高企是真实数据不是脏数据：东方财富证券、华林证券注册地均在拉萨，
   该榜是「券商注册地口径」，不代表「哪里人爱炒股」。西藏行予以保留。
"""
import argparse
import csv
import datetime as _dt
import os
import sys
import time

import akshare as ak

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(WS, 'data', 'topics_csv', 'szse_area.csv')

START = (2004, 12)
END = (2026, 7)         # 缺省值；--end-auto 时会按实际已披露月份自动收窄
COL = '股票交易额'          # 只要股票成交，剔除基金/债券/期权，口径更干净
MERGE_GD = {'广东', '深圳', '广州'}


def probe_latest_month():
    """自动探测深交所已披露的最新月份（月度数据次月上旬发布，故从「上月」往回试）。"""
    today = _dt.date.today()
    y, m = today.year, today.month - 1
    if m == 0:
        y, m = y - 1, 12
    for _ in range(6):
        try:
            df = ak.stock_szse_area_summary(date=f'{y}{m:02d}')
            if df is not None and len(df) > 0:
                return (y, m)
        except Exception:
            pass
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return None


def months(s, e):
    y, m = s
    out = []
    while (y, m) <= e:
        out.append(f'{y}-{m:02d}')
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def main():
    global END
    ap = argparse.ArgumentParser()
    ap.add_argument('--end-auto', action='store_true',
                    help='自动探测已披露的最新月份，覆盖内置 END')
    a = ap.parse_args()
    if a.end_auto:
        got = probe_latest_month()
        if got:
            END = got
            print(f'[auto] 探测到深交所最新已披露月份：{END[0]}-{END[1]:02d}')
        else:
            print('[auto] 探测失败，沿用内置 END =', END)
    ms = months(START, END)
    print(f'抓取区间 {ms[0]} ~ {ms[-1]}（{len(ms)} 个月）')
    data = {}
    fail = []
    for i, ym in enumerate(ms):
        d = ym.replace('-', '')
        try:
            df = ak.stock_szse_area_summary(date=d)
        except Exception as ex:
            fail.append((ym, str(ex)[:60]))
            continue
        if df is None or len(df) == 0:
            fail.append((ym, '空表'))
            continue
        rec = {}
        gd = 0.0
        gd_hit = False
        for _, r in df.iterrows():
            area = str(r['地区']).strip()
            try:
                v = float(r[COL])
            except (TypeError, ValueError):
                continue
            if area in MERGE_GD:
                gd += v
                gd_hit = True
                continue
            rec[area] = v
        if gd_hit:
            rec['广东(含深穗)'] = gd
        # 元 -> 亿元
        for k in list(rec):
            rec[k] = rec[k] / 1e8
        data[ym] = rec
        if (i + 1) % 20 == 0 or i == len(ms) - 1:
            print(f'  {i + 1}/{len(ms)} {ym} 完成', flush=True)
        time.sleep(0.25)

    print(f'成功 {len(data)} 月，失败 {len(fail)} 月')
    for f in fail[:10]:
        print('   失败:', f)

    # 只保留在末年仍有值、且历史累计足够大的地区（剔除僵尸行）
    areas = set()
    for rec in data.values():
        areas |= set(rec)
    last = ms[-1]
    keep = [a for a in areas
            if data.get(last, {}).get(a, 0) > 0
            and sum(1 for rec in data.values() if rec.get(a, 0) > 0) >= len(data) * 0.5]
    print(f'地区 {len(areas)} -> 保留 {len(keep)}')

    order = sorted(keep, key=lambda a: data.get(last, {}).get(a, 0), reverse=True)
    with open(OUT, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['name'] + ms)
        for a in order:
            w.writerow([a] + [f'{data[ym].get(a, 0):.0f}' if data[ym].get(a, 0) > 0 else ''
                              for ym in ms])
    print('写出', OUT)
    print('末年 Top10:', [(a, round(data[last].get(a, 0))) for a in order[:10]])


if __name__ == '__main__':
    main()
