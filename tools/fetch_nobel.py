# -*- coding: utf-8 -*-
"""诺贝尔奖（按出生国累计）刷新：只追加「API 里出现、CSV 里还没有」的新年份列。

口径说明（与既有 nobel.csv 保持一致，实测美国 2025 累计 = 296，与 API 完全吻合）：
  * 数据源：https://api.nobelprize.org/2.1/laureates
  * 归属：laureate.birth.place.country.en（出生地当时的国家），历史国名（Prussia /
    USSR / Austria-Hungary / British India 等）按映射表归入现代国家
  * 取值：按 awardYear 逐年累加 → 累计值
  * 安全：只追加新年份列；已有列一律不改写（避免口径漂移把历史数据改坏）

用法：
  python fetch_nobel.py              # 刷新 data/topics_csv/nobel.csv
  python fetch_nobel.py --check      # 只比对不写盘
"""
import argparse
import csv
import json
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CSV = os.path.join(WS, "data", "topics_csv", "nobel.csv")

# 中文国名 -> API 里可能出现的英文国名（含历史国名/地区）
CN2EN = {
    "美国": ["USA"],
    "英国": ["United Kingdom", "Scotland", "Northern Ireland"],
    "德国": ["Germany", "Prussia", "West Germany", "Bavaria", "Württemberg",
             "Mecklenburg", "Hesse-Kassel", "East Friesland", "Schleswig"],
    "法国": ["France", "Guadeloupe, France"],
    "日本": ["Japan"],
    "瑞典": ["Sweden"],
    "俄罗斯": ["Russia", "Russian Empire", "USSR"],
    "波兰": ["Poland", "Free City of Danzig", "German-occupied Poland"],
    "加拿大": ["Canada"],
    "荷兰": ["the Netherlands"],
    "意大利": ["Italy", "Tuscany"],
    "瑞士": ["Switzerland"],
    "奥地利": ["Austria", "Austria-Hungary", "Austrian Empire"],
    "挪威": ["Norway"],
    "丹麦": ["Denmark", "Faroe Islands (Denmark)"],
    "匈牙利": ["Hungary"],
    "中国": ["China", "Tibet"],
    "澳大利亚": ["Australia"],
    "印度": ["India", "British India"],
    "比利时": ["Belgium", "Belgian Congo"],
    "南非": ["South Africa"],
    "西班牙": ["Spain"],
    "以色列": ["Israel", "British Mandate of Palestine",
               "British Protectorate of Palestine"],
    "埃及": ["Egypt"],
    "捷克": ["Czechoslovakia", "Czech Republic", "Czechia"],
    "芬兰": ["Finland"],
    "爱尔兰": ["Ireland"],
    "乌克兰": ["Ukraine"],
    "阿根廷": ["Argentina"],
    "土耳其": ["Turkey", "Ottoman Empire"],
    "罗马尼亚": ["Romania"],
    "白俄罗斯": ["Belarus", "Byelorussia"],
    "立陶宛": ["Lithuania"],
    "巴基斯坦": ["Pakistan"],
    "新西兰": ["New Zealand"],
    "墨西哥": ["Mexico"],
    "韩国": ["Korea", "South Korea"],
    "伊朗": ["Iran", "Persia"],
}


def fetch_laureates():
    url = "https://api.nobelprize.org/2.1/laureates?limit=2000&sort=asc"
    req = urllib.request.Request(url, headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def build_panel(laureates):
    """返回 {中文国名: {年份: 当年获奖人次}}（只统计 CSV 里已有的国家）。"""
    en2cn = {}
    for cn, ens in CN2EN.items():
        for e in ens:
            en2cn[e.strip().lower()] = cn
    yearly = {}
    for L in laureates or []:
        pl = (L.get("birth") or {}).get("place") or {}
        c = (pl.get("country") or {}).get("en") or ""
        cn = en2cn.get(c.strip().lower())
        if not cn:
            continue
        prizes = L.get("nobelPrizes") or []
        if not prizes:
            continue
        y = prizes[0].get("awardYear") or ""
        try:
            y = int(y)
        except (TypeError, ValueError):
            continue
        if y <= 0:
            continue
        yearly.setdefault(cn, {})
        yearly[cn][y] = yearly[cn].get(y, 0) + 1
    return yearly


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--check", action="store_true", help="只比对不写盘")
    a = ap.parse_args()

    rows = list(csv.reader(open(a.csv, encoding="utf-8-sig", newline="")))
    head = [c.strip() for c in rows[0]]
    years = [c for c in head[1:] if c]
    names = [r[0].strip() for r in rows[1:] if r and r[0].strip()]
    cur = {r[0].strip(): r[1:] for r in rows[1:] if r and r[0].strip()}
    last = int(years[-1])
    print("[nobel] %s：%d 国 × %d 年（%s ~ %s）" % (a.csv, len(names), len(years), years[0], last))

    d = fetch_laureates()
    yearly = build_panel(d.get("laureates", []))
    api_years = sorted({y for v in yearly.values() for y in v})
    print("  API 获奖年份范围：%s ~ %s" % (api_years[0], api_years[-1]))

    new_years = [y for y in api_years if y > last]
    if not new_years:
        print("  无新增年份（末年 %s 已是 API 最新），跳过" % last)
        # 顺带校验末年累计值是否与 API 一致
        bad = []
        for n in names:
            api = sum(v for y, v in yearly.get(n, {}).items() if y <= last)
            try:
                csvv = float((cur[n][len(years) - 1] or "").strip() or 0)
            except (ValueError, IndexError):
                csvv = 0.0
            if abs(api - csvv) > 0.5:
                bad.append((n, csvv, api))
        if bad:
            print("  ⚠ 末年累计值不一致 %d 处（不自动改写，供人工核对）：" % len(bad))
            for n, c1, c2 in bad[:12]:
                print("     %-8s CSV=%-6g API=%g" % (n, c1, c2))
        else:
            print("  ✓ 末年累计值与 API 完全一致（%d 国）" % len(names))
        return 0

    print("  将追加年份：%s ~ %s" % (new_years[0], new_years[-1]))
    if a.check:
        return 0

    out_years = years + [str(y) for y in new_years]
    # 逐年累计
    cum = {n: 0 for n in names}
    for n in names:
        try:
            cum[n] = float((cur[n][len(years) - 1] or "").strip() or 0)
        except (ValueError, IndexError):
            cum[n] = 0.0
    with open(a.csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name"] + out_years)
        for n in names:
            row = list(cur[n])
            for y in new_years:
                cum[n] += yearly.get(n, {}).get(y, 0)
                row.append("%g" % cum[n])
            w.writerow([n] + row)
    print("  写出 %s：%d 国 × %d 年" % (a.csv, len(names), len(out_years)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
