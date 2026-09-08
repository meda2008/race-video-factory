#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""全量核对：每个题材 CSV 的「末年 / 粒度」vs 上游实际最新时间，判断是否落后。

用法: python scripts_local/check_fresh.py [--upstream-json probe_out.json]
无 json 时用内置的上游基线（来自 probe_upstream.py 实测，需定期重跑更新）。
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(HERE)
CSV_DIR = os.path.join(WS, "data", "topics_csv")

# 上游最新时间基线（2026-09-07 probe_upstream.py 实测）
UPSTREAM = {
    # OWID slug -> 最新年
    "owid:annual-co2-emissions-per-country": 2024,
    "owid:life-expectancy": 2023,
    "owid:child-mortality": 2024,
    "owid:oil-production-by-country": 2025,
    "owid:primary-energy-cons": 2025,
    "owid:share-electricity-low-carbon": 2025,
    "owid:share-of-adults-defined-as-obese": 2024,
    "owid:beer-consumption-per-person": 2022,
    "owid:co-emissions-per-capita": 2024,
    "owid:electricity-generation": 2025,
    "owid:nuclear-energy-generation": 2025,
    "owid:gas-production-by-country": 2025,
    "owid:coal-production-by-country": 2025,
    "owid:cumulative-co-emissions": 2024,
    # 世行 WDI 指标 -> 最新年
    "wdi:NY.GDP.MKTP.CD": 2025, "wdi:SP.POP.TOTL": 2025,
    "wdi:IS.AIR.PSGR": 2023, "wdi:IP.PAT.RESD": 2021,
    "wdi:NE.TRD.GNFS.ZS": 2025, "wdi:NY.GDP.PCAP.CD": 2025,
    "wdi:FI.RES.TOTL.CD": 2025, "wdi:FP.CPI.TOTL.ZG": 2025,
    "wdi:FM.LBL.BMNY.GD.ZS": 2025, "wdi:MS.MIL.XPND.CD": 2024,
    # 其他通道
    "ashare": "2026Q2", "us": "2026Q2", "szse": "2026-08", "nobel": 2025,
}

# 题材 -> 上游通道键（None 表示人工/无自动通道）
TOPIC_SRC = {
    "annual_co2": "owid:annual-co2-emissions-per-country",
    "life_expectancy": "owid:life-expectancy",
    "child_mortality": "owid:child-mortality",
    "oil_production": "owid:oil-production-by-country",
    "primary_energy": "owid:primary-energy-cons",
    "low_carbon_pct": "owid:share-electricity-low-carbon",
    "obesity_rate": "owid:share-of-adults-defined-as-obese",
    "beer_per_capita": "owid:beer-consumption-per-person",
    "co2_per_capita": "owid:co-emissions-per-capita",
    "electricity": "owid:electricity-generation",
    "nuclear_energy": "owid:nuclear-energy-generation",
    "gas_production": "owid:gas-production-by-country",
    "coal_production": "owid:coal-production-by-country",
    "cumulative_co2": "owid:cumulative-co-emissions",
    "air_passengers": "wdi:IS.AIR.PSGR",
    "patents": "wdi:IP.PAT.RESD",
    "trade_gdp": "wdi:NE.TRD.GNFS.ZS",
    "cpi": "wdi:FP.CPI.TOTL.ZG",
    "m2_gdp": "wdi:FM.LBL.BMNY.GD.ZS",
    "gdp_per_capita": "wdi:NY.GDP.PCAP.CD",
    "stock_mcap": None,
    "nobel": "nobel",
    "szse_area": "szse",
    # A股（东财三大表 / 分红）
    "ashare_profit": "ashare", "ashare_loss": "ashare", "ashare_revenue": "ashare",
    "ashare_sellexp": "ashare", "ashare_cash": "ashare", "ashare_receivable": "ashare",
    "ashare_ocf": "ashare", "ashare_industry_cap": "ashare",
    "ashare_dividend": "ashare",
    # 美股单季报
    "ai_capex": "us", "chip_revenue": "us", "defense_revenue": "us",
    "pharma_revenue": "us", "semiequip_revenue": "us", "mining_revenue": "us",
    # 人工 / 特殊
    "brands": None, "brands_top": None, "gold_reserves": None,
    "world_top10_houseprice": None, "market_cap": None,
}


def csv_tail(fn):
    p = os.path.join(CSV_DIR, fn)
    r = list(csv.reader(io.open(p, encoding="utf-8-sig")))
    cols = [c for c in r[0][1:] if c.strip()]
    if not cols:
        return None, None, 0, 0, 0
    last = cols[-1]
    if "Q" in last:
        g = "季度"
    elif len(last) == 7 and "-" in last:
        g = "月度"
    else:
        g = "年度"
    n = sum(1 for row in r[1:] if row and len(row) > len(cols) and row[len(cols)].strip())
    return cols[0], last, g, len(cols), n / max(1, len(r) - 1)


def to_num(x):
    """'2026Q2'/'2026-08'/2025 -> 可比较数值"""
    s = str(x)
    if "Q" in s:
        y, q = s.split("Q")
        return int(y) + int(q) * 0.25
    if "-" in s and len(s) == 7:
        y, m = s.split("-")
        return int(y) + int(m) / 12
    try:
        return float(s)
    except ValueError:
        return None


def main():
    up = UPSTREAM
    if "--upstream-json" in sys.argv:
        j = sys.argv[sys.argv.index("--upstream-json") + 1]
        up = json.load(io.open(j, encoding="utf-8"))

    lag, ok, manual = [], [], []
    for fn in sorted(os.listdir(CSV_DIR)):
        if not fn.endswith(".csv") or fn.startswith("_bak"):
            continue
        key = fn[:-4]
        first, last, g, ncol, cov = csv_tail(fn)
        if last is None:
            continue
        src = TOPIC_SRC.get(key, "?")
        if src is None:
            manual.append((key, last, g, ncol, cov, "人工/无自动通道"))
            continue
        if src not in up or src == "?":
            manual.append((key, last, g, ncol, cov, "未登记通道"))
            continue
        u = up[src]
        a, b = to_num(last), to_num(u)
        if a is None or b is None:
            manual.append((key, last, g, ncol, cov, f"上游={u} 无法比较"))
        elif a + 1e-9 < b:
            lag.append((key, last, g, ncol, cov, u, src))
        else:
            ok.append((key, last, g, ncol, cov, u))

    print("=" * 92)
    print(f"⚠️  落后于上游：{len(lag)} 个")
    print("=" * 92)
    if lag:
        print(f'{"题材":24s} {"CSV末年":>9s} {"粒度":4s} {"上游":>9s} {"末列覆盖":>7s}  通道')
        for k, last, g, ncol, cov, u, src in lag:
            print(f"{k:24s} {last:>9s} {g:4s} {str(u):>9s} {cov:7.0%}  {src}")
    else:
        print("  （无）")

    print()
    print("=" * 92)
    print(f"✅ 已跟上上游：{len(ok)} 个")
    print("=" * 92)
    print(f'{"题材":24s} {"起":>8s} {"止":>9s} {"粒度":4s} {"列":>4s} {"末列覆盖":>7s}  上游')
    for k, last, g, ncol, cov, u in ok:
        print(f"{k:24s} {'':>8s} {last:>9s} {g:4s} {ncol:4d} {cov:7.0%}  {u}")

    print()
    print("=" * 92)
    print(f"🔧 人工/无自动通道：{len(manual)} 个")
    print("=" * 92)
    for k, last, g, ncol, cov, why in manual:
        print(f"{k:24s} {last:>9s} {g:4s} {ncol:4d} {cov:7.0%}  {why}")


if __name__ == "__main__":
    main()
