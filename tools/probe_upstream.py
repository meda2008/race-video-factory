#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""探测各数据通道「上游实际最新时间」，用于判断题材 CSV 是否落后。

用法: python scripts_local/probe_upstream.py
输出: 每个通道的最新可用报告期/年份/月份。
"""
from __future__ import annotations

import io
import json
import os
import ssl
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(WS, "scripts_local"))

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

out = {}


def sec(title):
    print("\n" + "=" * 14 + " " + title + " " + "=" * 14)


# ── 1. A股三大表 ────────────────────────────────────────────────
sec("A股（akshare 东财）")
try:
    import akshare as ak
    # 东财三大表：date 决定报告期，返回宽表（列名是「股票简称」「股票代码」等）
    for period in ("20251231", "20260331", "20260630", "20260930"):
        got = []
        for fn, name in (("stock_lrb_em", "利润表"), ("stock_zcfz_em", "资产负债表"),
                         ("stock_xjll_em", "现金流量表")):
            try:
                df = getattr(ak, fn)(date=period)
                got.append(f"{name}={len(df)}行")
            except Exception:  # noqa: BLE001
                got.append(f"{name}=无")
        print(f"  {period}: " + "  ".join(got))
except ImportError:
    print("  akshare 未安装")


# ── 2. A股分红（年报口径）────────────────────────────────────────
try:
    import akshare as ak
    df = ak.stock_fhps_em(date="20251231")
    print(f"  分红      stock_fhps_em     20251231 行={len(df)}")
    out["ashare_dividend"] = "20251231"
except Exception as e:  # noqa: BLE001
    print(f"  分红      ERR {repr(e)[:80]}")


# ── 3. 美股财报 ─────────────────────────────────────────────────
sec("美股（akshare 单季报）")
try:
    import akshare as ak
    from collections import Counter
    # 注意参数语义：stock=股票代码, symbol=报表名（综合损益表/现金流量表）
    uni = [("微软", "MSFT"), ("苹果", "AAPL"), ("谷歌", "GOOGL"), ("亚马逊", "AMZN"),
           ("脸书", "META"), ("英伟达", "NVDA"), ("礼来", "LLY"), ("超威", "AMD")]
    cnt = Counter()
    for cn, sym in uni:
        try:
            df = ak.stock_financial_us_report_em(stock=sym, symbol="综合损益表",
                                                 indicator="单季报")
            ds = sorted({str(x)[:10] for x in df["REPORT_DATE"]})[-3:]
            for d in ds:
                cnt[d] += 1
            print(f"  {cn:6s} 最近报告期 {ds}")
        except Exception as e:  # noqa: BLE001
            print(f"  {cn:6s} ERR {repr(e)[:70]}")
    print("  各家覆盖统计（报告期: 家数）:", dict(sorted(cnt.items())[-6:]))
    out["us"] = dict(sorted(cnt.items())[-6:])
except Exception as e:  # noqa: BLE001
    print(f"  ERR {repr(e)[:100]}")


# ── 4. 深交所分地区 ─────────────────────────────────────────────
sec("深交所（分地区月度）")
try:
    import akshare as ak
    for ym in ("202608", "202609", "202607"):
        try:
            df = ak.stock_szse_area_summary(date=ym)
            print(f"  stock_szse_area_summary({ym}) 行={len(df)}")
            out.setdefault("szse", ym)
            break
        except Exception as e:  # noqa: BLE001
            print(f"  {ym} ERR {repr(e)[:60]}")
except Exception as e:  # noqa: BLE001
    print(f"  ERR {repr(e)[:100]}")


# ── 5. 世行 WDI ─────────────────────────────────────────────────
sec("世行 WDI")
WDI_IND = {
    "NY.GDP.MKTP.CD": "GDP", "SP.POP.TOTL": "人口",
    "IS.AIR.PSGR": "航空客运", "IP.PAT.RESD": "专利",
    "NE.TRD.GNFS.ZS": "贸易占GDP", "NY.GDP.PCAP.CD": "人均GDP",
    "FI.RES.TOTL.CD": "外储", "MS.MIL.XPND.CD": "军费",
    "FP.CPI.TOTL.ZG": "CPI", "FM.LBL.BMNY.GD.ZS": "M2占GDP",
}
for ind, nm in WDI_IND.items():
    try:
        url = ("https://api.worldbank.org/v2/country/all/indicator/%s"
               "?format=json&per_page=3000&date=2018:2027" % ind)
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
            meta = json.loads(r.read().decode("utf-8"))
        rows = meta[1] or []
        yrs = sorted({int(x["date"]) for x in rows if x.get("value") is not None})
        # 末年有多少国家上报
        if yrs:
            mx = yrs[-1]
            n = sum(1 for x in rows if int(x["date"]) == mx and x.get("value") is not None)
            print(f"  {nm:10s} {ind:18s} 最新={mx}  该年上报国数={n}")
            out["wdi_" + ind] = (mx, n)
        else:
            print(f"  {nm:10s} {ind:18s} 无数据")
    except Exception as e:  # noqa: BLE001
        print(f"  {nm:10s} ERR {repr(e)[:60]}")


# ── 6. OWID ─────────────────────────────────────────────────────
sec("OWID")
try:
    import pandas as pd
    from io import StringIO
    import requests
    OWID = {
        "annual-co2-emissions-per-country": "碳排放",
        "life-expectancy": "预期寿命",
        "child-mortality": "儿童死亡率",
        "oil-production-by-country": "石油产量",
        "primary-energy-cons": "一次能源",
        "share-electricity-low-carbon": "低碳电力",
        "share-of-adults-defined-as-obese": "肥胖率",
        "beer-consumption-per-person": "啤酒消费",
        "co-emissions-per-capita": "人均碳排",
        "electricity-generation": "发电量",
        "nuclear-energy-generation": "核电",
        "gas-production-by-country": "天然气",
        "coal-production-by-country": "煤炭",
        "cumulative-co-emissions": "累计碳排",
    }
    for slug, nm in OWID.items():
        mx = n = None
        for attempt in range(3):          # OWID 偶发 SSL/超时，重试 3 次
            try:
                url = f"https://ourworldindata.org/grapher/{slug}.csv?v=1&csvType=full"
                r = requests.get(url, headers=UA, timeout=90)
                df = pd.read_csv(StringIO(r.text))
                mx = int(df["Year"].max())
                n = int((df["Year"] == mx).sum())
                break
            except Exception:  # noqa: BLE001
                import time
                time.sleep(2)
        if mx is None:
            print(f"  {nm:8s} {slug:38s} ERR 三次重试均失败")
        else:
            print(f"  {nm:8s} {slug:38s} 最新={mx}  该年实体数={n}")
            out["owid_" + slug] = (mx, n)
except Exception as e:  # noqa: BLE001
    print(f"  ERR {repr(e)[:100]}")


# ── 7. 诺贝尔奖 ─────────────────────────────────────────────────
sec("诺贝尔奖")
try:
    url = "https://api.nobelprize.org/2.1/laureates?limit=2000&sort=desc"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=90, context=CTX) as r:
        d = json.loads(r.read().decode("utf-8"))
    yrs = []
    for L in d.get("laureates", []):
        pz = L.get("nobelPrizes") or []
        if pz and pz[0].get("awardYear"):
            yrs.append(int(pz[0]["awardYear"]))
    print(f"  API 最新获奖年 = {max(yrs) if yrs else '?'}  （样本 {len(yrs)} 人）")
    out["nobel"] = max(yrs) if yrs else None
except Exception as e:  # noqa: BLE001
    print(f"  ERR {repr(e)[:80]}")


print("\n" + "=" * 50)
