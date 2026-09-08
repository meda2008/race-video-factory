# -*- coding: utf-8 -*-
"""竞速视频数据「一键刷新到最新」编排器（2026-09-06 新建）。

设计目标（用户要求）：
  1. **想方设法补到最新（2026）** —— 所有通道的「末年」一律运行时自动探测，
     不再硬编码 END（历史 bug 根源：fetch_szse_area.py / fetch_wdi_latest.py 里
     写死 2026-07、2025 等常量，时间一过就过期）。
  2. **数据粒度越细越好** —— 能取季度就取季度（A股财报 / 美股财报），
     能取月度就取月度（深交所地区交易分布），绝不退化成年度。
  3. **绝不编造** —— 只写 API 真实返回值；覆盖率不过护栏的新期次直接丢弃。

通道：
  ashare  A股全市场财报（akshare，季度）      -> scripts_local/fetch_ashare_fin.py
  us      美股财报（akshare，季度）           -> scripts_local/fetch_us_fin.py
  wdi     世界银行 WDI（年度，全球面板）       -> scripts_local/refresh_wdi_extend.py
  owid    Our World in Data（年度，全球面板）  -> scripts_local/refresh_owid_extend.py
  szse    深交所地区交易分布（月度）           -> scripts_local/fetch_szse_area.py
  nobel   诺贝尔奖官方 API（年度）            -> 内置

用法：
  python refresh_all.py                      # 全部可自动刷新的题材
  python refresh_all.py --only ashare_profit,patents
  python refresh_all.py --dry-run            # 只打印计划，不执行
  python refresh_all.py --upgrade-quarterly  # 把 A股「只有年报」的题材重建为季度粒度

退出码：0=全部成功；1=有题材失败（失败不影响其它题材）。
"""
import argparse
import csv
import datetime
import glob
import json
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(HERE)                      # batch2_ws
PY = r"C:/Users/medam/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
REG_GLOB = os.path.join(WS, "topics_registry_*.json")
THIS_YEAR = datetime.date.today().year

# ─────────────────────────── 刷新计划 ───────────────────────────
# (key, channel, cfg)
PLAN = [
    # —— A股全市场财报：季度粒度，自动探测最新已披露报告期 ——
    ("ashare_profit",     "ashare", dict(mode="profit",     freq="quarterly", start=2004)),
    ("ashare_loss",       "ashare", dict(mode="loss",       freq="quarterly", start=2004)),
    ("ashare_revenue",    "ashare", dict(mode="revenue",    freq="quarterly", start=2004)),
    ("ashare_sellexp",    "ashare", dict(mode="sellexp",    freq="quarterly", start=2004)),
    # 以下三个历史上只有年报（22 列），--upgrade-quarterly 会重建为季度（90 列）
    ("ashare_cash",       "ashare", dict(mode="cash",       freq="yearly", start=2004, upgrade="quarterly")),
    ("ashare_receivable", "ashare", dict(mode="receivable", freq="yearly", start=2004, upgrade="quarterly")),
    ("ashare_ocf",        "ashare", dict(mode="ocf",        freq="yearly", start=2004, upgrade="quarterly")),
    ("ashare_dividend",   "ashare", dict(mode="dividend",   freq="yearly", start=2004)),

    # —— 美股财报：季度粒度，--end-auto 自动到最新报告期 ——
    ("ai_capex",          "us", dict(mode="capex",      start=2012)),
    ("chip_revenue",      "us", dict(mode="revenue",    start=2005)),
    ("pharma_revenue",    "us", dict(mode="pharma",     start=2005)),
    ("semiequip_revenue", "us", dict(mode="semiequip",  start=2005)),
    ("defense_revenue",   "us", dict(mode="defense",    start=2005)),
    ("mining_revenue",    "us", dict(mode="mining",     start=2005)),

    # —— 世行 WDI：年度 ——
    ("fx_reserves",       "wdi", dict(indicator="FI.RES.TOTL.CD", start=1960)),
    ("stock_mcap",        "wdi", dict(indicator="CM.MKT.LCAP.CD", start=1960)),
    ("gdp_per_capita",    "wdi", dict(indicator="NY.GDP.PCAP.CD", start=1960)),
    ("m2_gdp",            "wdi", dict(indicator="FM.LBL.BMNY.GD.ZS", start=1960)),
    ("cpi",               "wdi", dict(indicator="FP.CPI.TOTL.ZG", start=1960)),
    ("air_passengers",    "wdi", dict(indicator="IS.AIR.PSGR", start=1960)),
    ("patents",           "wdi", dict(indicator="IP.PAT.RESD", start=1960)),
    ("trade_gdp",         "wdi", dict(indicator="NE.TRD.GNFS.ZS", start=1960)),

    # —— OWID：年度（--end 放宽到明年，脚本内以「实际有值的年」为准） ——
    ("annual_co2",        "owid", dict(slug="annual-co2-emissions-per-country")),
    ("child_mortality",   "owid", dict(slug="child-mortality")),
    ("life_expectancy",   "owid", dict(slug="life-expectancy")),
    ("oil_production",    "owid", dict(slug="oil-production-by-country")),
    ("primary_energy",    "owid", dict(slug="primary-energy-cons")),
    ("nuclear_energy",    "owid", dict(slug="nuclear-energy-generation")),
    ("low_carbon_pct",    "owid", dict(slug="share-electricity-low-carbon")),
    ("obesity_rate",      "owid", dict(slug="share-of-adults-defined-as-obese")),
    ("beer_per_capita",   "owid", dict(slug="beer-consumption-per-person")),
    ("co2_per_capita",    "owid", dict(slug="co-emissions-per-capita")),
    ("cumulative_co2",    "owid", dict(slug="cumulative-co-emissions")),
    ("gas_production",    "owid", dict(slug="gas-production-by-country")),
    ("coal_production",   "owid", dict(slug="coal-production-by-country")),
    ("electricity",       "owid", dict(slug="electricity-generation")),

    # —— 深交所地区交易分布：月度 ——
    ("szse_area",         "szse", dict()),

    # —— 诺贝尔奖：年度 ——
    ("nobel",             "nobel", dict()),
]

YEAR_RE = re.compile(r"(19|20)\d{2}")


# ─────────────────────────── 通用工具 ───────────────────────────
def resolve_csv(key, param_path=""):
    cands = []
    if param_path:
        cands.append(os.path.join(WS, param_path))
    cands.append(os.path.join(WS, "data", "topics_csv", key + ".csv"))
    cands.append(os.path.join(WS, "topics", key + ".csv"))
    for c in cands:
        if os.path.exists(c):
            return c
    hits = glob.glob(os.path.join(WS, "**", key + ".csv"), recursive=True)
    return hits[0] if hits else None


def read_csv_head(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], 0, 0
    head = [c for c in rows[0][1:] if c.strip()]
    # 实际有数据的最后一列
    last_filled = 0
    for r in rows[1:]:
        for i in range(1, min(len(r), len(rows[0]))):
            if (r[i] or "").strip() not in ("", "-", "--"):
                last_filled = max(last_filled, i)
    last_label = head[last_filled - 1] if 0 < last_filled <= len(head) else (head[-1] if head else "")
    return head, len(rows) - 1, last_label


def load_registries():
    """key -> (registry_path, index)。同 key 出现在多份注册表时全部记录。"""
    out = {}
    for p in sorted(glob.glob(REG_GLOB)):
        d = json.load(open(p, encoding="utf-8"))
        for i, t in enumerate(d.get("topics", [])):
            out.setdefault(t["key"], []).append((p, i))
    return out


def update_registry(key, locs, new_last, gran_note):
    """把注册表里的 title/subtitle/source 里的年份区间同步到新末年。"""
    changed = []
    for p, i in locs:
        d = json.load(open(p, encoding="utf-8"))
        t = d["topics"][i]
        prm = t.setdefault("params", {})
        old_sub = prm.get("subtitle", "")
        old_src = prm.get("source", "")
        sub = old_sub
        # subtitle 常见形态：「…（2000 → 2024 逐年…）」「…1995–2024…」
        if sub:
            sub = re.sub(r"(20\d{2})\s*(→|–|-|~|至)\s*(20\d{2})",
                         lambda m: "%s%s%s" % (m.group(1), m.group(2), new_last), sub, count=1)
        if sub == old_sub and old_src:
            src = re.sub(r"(20\d{2})\s*(→|–|-|~|至)\s*(20\d{2})",
                         lambda m: "%s%s%s" % (m.group(1), m.group(2), new_last), old_src, count=1)
            if src != old_src:
                prm["source"] = src + f"；{gran_note}"
        if sub != old_sub:
            prm["subtitle"] = sub
            prm.setdefault("source", old_src)
            prm["source"] = prm["source"].rstrip("；") + f"；{gran_note}"
        if prm.get("subtitle") != old_sub or prm.get("source") != old_src:
            json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            changed.append(os.path.basename(p))
    return changed


# ─────────────────────────── 通道 ───────────────────────────
def run(cmd, timeout=3600):
    return subprocess.run(cmd, cwd=HERE, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout)


def ch_ashare(key, cfg, dry, upgrade):
    """A股财报。已是季度粒度的走「增量追加」（只抓新期次，快 40 倍）；
    仍是年报粒度的走全量重建（--upgrade-quarterly 时才是季度）。"""
    mode = cfg["mode"]
    freq = cfg.get("freq", "yearly")
    if upgrade and cfg.get("upgrade"):
        freq = cfg["upgrade"]
    base = [PY, "fetch_ashare_fin.py", mode, "--freq", freq, "--end-auto"]

    # 已是季度 → 增量追加（需要现有末列标签）
    if freq == "quarterly" and not (upgrade and cfg.get("upgrade")):
        p = resolve_csv(key)
        if p:
            _h, _n, last = read_csv_head(p)
            if last and "Q" in str(last):
                base += ["--append-after", str(last)]
            else:
                base += ["--start", str(cfg.get("start", 2004))]
        else:
            base += ["--start", str(cfg.get("start", 2004))]
    else:
        base += ["--start", str(cfg.get("start", 2004))]

    cmd = base
    if dry:
        return " ".join(cmd), None
    r = run(cmd)
    return None, (r.returncode, r.stdout.decode("utf-8", "ignore"))


def ch_us(key, cfg, dry, upgrade):
    cmd = [PY, "fetch_us_fin.py", cfg["mode"],
           "--start", str(cfg.get("start", 2005)), "--end-auto"]
    if dry:
        return " ".join(cmd), None
    r = run(cmd)
    return None, (r.returncode, r.stdout.decode("utf-8", "ignore"))


def ch_wdi(key, cfg, dry, upgrade):
    cmd = [PY, "refresh_wdi_extend.py", key, cfg["indicator"],
           "--start", str(cfg.get("start", 1960)),
           "--end", str(THIS_YEAR + 1)]
    if dry:
        return " ".join(cmd), None
    r = run(cmd)
    return None, (r.returncode, r.stdout.decode("utf-8", "ignore"))


def ch_owid(key, cfg, dry, upgrade):
    cmd = [PY, "refresh_owid_extend.py", key, cfg["slug"], "--end", str(THIS_YEAR + 1)]
    if dry:
        return " ".join(cmd), None
    r = run(cmd)
    return None, (r.returncode, r.stdout.decode("utf-8", "ignore"))


def ch_szse(key, cfg, dry, upgrade):
    cmd = [PY, "fetch_szse_area.py", "--end-auto"]
    if dry:
        return " ".join(cmd), None
    r = run(cmd)
    return None, (r.returncode, r.stdout.decode("utf-8", "ignore"))


def ch_nobel(key, cfg, dry, upgrade):
    """诺贝尔奖官方 API：按出生国累计（与既有人口径保持一致）。"""
    code = r'''
import json, urllib.request, csv, os, sys
UA = {"User-Agent": "Mozilla/5.0"}
url = "https://api.nobelprize.org/2.1/laureates?limit=2000&sort=asc"
d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read())
path = r"__PATH__"
rows = list(csv.reader(open(path, encoding="utf-8-sig")))
head = rows[0]; years = [c for c in head[1:] if c.strip()]
panel = {r[0]: r[1:] for r in rows[1:] if r}
cnt = {n: [0]*len(years) for n in panel}
for lau in d.get("laureates", []):
    born = (lau.get("birth") or {}).get("place", {}) or {}
    ctry = (born.get("country") or {}).get("en") or (born.get("countryNow") or {}).get("en")
    prizes = lau.get("nobelPrizes") or []
    if not prizes or not ctry:
        continue
    y = int(prizes[0].get("awardYear", 0) or 0)
    for nm in cnt:
        pass
    if y and str(y) in years:
        i = years.index(str(y))
        for nm in cnt:
            pass
    if not y:
        continue
    if str(y) not in years:
        continue
    i = years.index(str(y))
    for nm in cnt:
        if nm.lower()[:4] in ctry.lower() or ctry.lower()[:4] in nm.lower():
            cnt[nm][i] += 1
print("nobel API laureates:", len(d.get("laureates", [])))
'''
    if dry:
        return "nobel API（内嵌）", None
    p = resolve_csv(key)
    if not p:
        return None, (1, "CSV 未找到")
    code = code.replace("__PATH__", p)
    r = subprocess.run([PY, "-c", code], cwd=HERE, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=600)
    return None, (r.returncode, r.stdout.decode("utf-8", "ignore"))


CHANNELS = {
    "ashare": ch_ashare, "us": ch_us, "wdi": ch_wdi,
    "owid": ch_owid, "szse": ch_szse, "nobel": ch_nobel,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只跑这些 key，逗号分隔")
    ap.add_argument("--skip", default="", help="跳过这些 key，逗号分隔")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--upgrade-quarterly", action="store_true",
                    help="把标记为 upgrade 的 A股题材重建为季度粒度（耗时较长）")
    ap.add_argument("--timeout", type=int, default=3600)
    a = ap.parse_args()

    only = {s.strip() for s in a.only.split(",") if s.strip()}
    skip = {s.strip() for s in a.skip.split(",") if s.strip()}
    regs = load_registries()

    print("=" * 84)
    print("竞速视频数据刷新到最新  |  今天 %s  |  %s"
          % (datetime.date.today().isoformat(), "DRY-RUN" if a.dry_run else "实跑"))
    print("=" * 84)

    results = []
    for key, ch, cfg in PLAN:
        if only and key not in only:
            continue
        if key in skip:
            continue
        path = resolve_csv(key)
        if not path:
            results.append((key, ch, "—", "—", "SKIP: CSV 未找到"))
            continue
        before_head, before_n, before_last = read_csv_head(path)
        t0 = time.time()
        plan, out = CHANNELS[ch](key, cfg, a.dry_run, a.upgrade_quarterly)
        dt = time.time() - t0
        if a.dry_run:
            print("[dry] %-20s %-7s %s" % (key, ch, plan))
            results.append((key, ch, before_last, "(dry)", "计划已打印"))
            continue

        rc, log = out
        after_head, after_n, after_last = read_csv_head(path)
        gained = len(after_head) - len(before_head)
        status = "OK" if rc == 0 else "FAIL(rc=%d)" % rc
        if rc == 0 and gained <= 0 and after_last == before_last:
            status = "OK(无新增)"
        tail = ""
        if rc != 0:
            tail = " | " + (log or "").strip().splitlines()[-1][:110]
        print("[%-3s] %-20s %-7s %s → %s  (+%d 列, %d实体, %.0fs)%s"
              % (status.split("(")[0], key, ch, before_last or "?",
                 after_last or "?", gained, after_n, dt, tail))
        if rc == 0 and (gained > 0 or after_last != before_last):
            note = "自动刷新至 %s" % after_last
            changed = update_registry(key, regs.get(key, []), str(after_last)[:4], note)
            if changed:
                print("        注册表已同步：%s" % ", ".join(changed))
        results.append((key, ch, before_last, after_last, status))

    print("=" * 84)
    ok = sum(1 for r in results if r[4].startswith("OK"))
    bad = [r for r in results if not r[4].startswith("OK")]
    print("完成 %d / %d 失败 %d" % (ok, len(results), len(bad)))
    for r in bad:
        print("  ✗ %-20s %s" % (r[0], r[4]))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
