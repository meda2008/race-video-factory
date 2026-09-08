# -*- coding: utf-8 -*-
"""生成「数据刷新报告」：所有题材的跨度 / 粒度 / 末列覆盖 / 数据来源 / 上游上限。"""
import csv
import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(WS), "数据刷新报告_%s.md" % "2026-09-06")

# key -> (通道, 上游最新, 备注)
UPSTREAM = {
    "ashare_profit": ("A股财报·季", "2026Q2", "东财全市场利润表，单季=累计差分"),
    "ashare_loss": ("A股财报·季", "2026Q2", "同上，取最负"),
    "ashare_revenue": ("A股财报·季", "2026Q2", "营业总收入"),
    "ashare_sellexp": ("A股财报·季", "2026Q2", "营业总支出-销售费用"),
    "ashare_cash": ("A股财报·季", "2026Q2", "资产负债表时点数，不做差分"),
    "ashare_receivable": ("A股财报·季", "2026Q2", "同上"),
    "ashare_ocf": ("A股财报·季", "2026Q2", "现金流量表累计→单季差分"),
    "ashare_dividend": ("A股分红·年", "2025", "仅年报口径，无法季度化"),
    "ai_capex": ("美股财报·季", "2026Q2", "2026Q3 仅 2/10 家披露，已截"),
    "chip_revenue": ("美股财报·季", "2026Q2", "2026Q3 仅 4/10 家披露，已截"),
    "pharma_revenue": ("美股财报·季", "2026Q2", ""),
    "semiequip_revenue": ("美股财报·季", "2026Q2", "2026Q3 仅 1/9 家披露，已截"),
    "defense_revenue": ("美股财报·季", "2026Q2", "2026Q3 仅 4/10 家披露，已截"),
    "mining_revenue": ("美股财报·季", "2026Q2", ""),
    "fx_reserves": ("世行WDI·年", "2025", "上游就到 2025"),
    "stock_mcap": ("世行WDI·年", "2025", ""),
    "gdp_per_capita": ("世行WDI·年", "2025", ""),
    "m2_gdp": ("世行WDI·年", "2024", "2025 仅 7/22 国上报，Top15 命中 47% 已截"),
    "cpi": ("世行WDI·年", "2025", "Top15 命中 60%，按宽松档保留"),
    "air_passengers": ("世行WDI·年", "2023", "上游就到 2023"),
    "patents": ("世行WDI·年", "2021", "上游就到 2021（IP.PAT.RESD 停更）"),
    "trade_gdp": ("世行WDI·年", "2025", ""),
    "annual_co2": ("OWID·年", "2024", "上游就到 2024"),
    "child_mortality": ("OWID·年", "2024", ""),
    "life_expectancy": ("OWID·年", "2023", "上游就到 2023"),
    "oil_production": ("OWID·年", "2025", "Top15 命中 100%，全表 26% 属正常"),
    "primary_energy": ("OWID·年", "2024", "2025 仅 88/226 国，已截"),
    "nuclear_energy": ("OWID·年", "2025", "Top15 命中 67%，按宽松档保留"),
    "low_carbon_pct": ("OWID·年", "2024", "2025 Top15 命中 47%，已截"),
    "obesity_rate": ("OWID·年", "2024", ""),
    "beer_per_capita": ("OWID·年", "2022", "上游就到 2022"),
    "co2_per_capita": ("OWID·年", "2024", ""),
    "cumulative_co2": ("OWID·年", "2024", ""),
    "gas_production": ("OWID·年", "2025", ""),
    "coal_production": ("OWID·年", "2025", ""),
    "electricity": ("OWID·年", "2025", ""),
    "szse_area": ("深交所·月", "2026-08", "分地区月度成交额"),
    "nobel": ("诺奖API·年", "2025", "2026 未公布（10 月）"),
    "gold_reserves": ("IMF·季", "2020Q1", "⛔ IMF 通道被封，暂无法更新"),
    "brands": ("Interbrand·年", "2021", "⛔ 需人工导入"),
    "world_top10_houseprice": ("人工·年", "2024", "⛔ 单列题材，需人工"),
}


def last_filled(rows):
    head = [c for c in rows[0][1:] if c.strip()]
    if not head:
        return "", 0
    for i in range(len(head) - 1, -1, -1):
        n = sum(1 for r in rows[1:]
                if i + 1 < len(r) and (r[i + 1] or "").strip() not in ("", "-", "--"))
        if n >= 3:
            return head[i], n
    return head[-1], 0


def main():
    reg = {}
    for p in sorted(glob.glob(os.path.join(WS, "topics_registry_*.json"))):
        d = json.load(open(p, encoding="utf-8"))
        for t in d.get("topics", []):
            prm = t.get("params") or {}
            reg[t["key"]] = (prm.get("path") or "", prm.get("subtitle", ""),
                             prm.get("title", ""))

    rows = []
    for key in sorted(reg):
        rel, sub, title = reg[key]
        cpath = os.path.join(WS, rel) if rel else ""
        if not cpath or not os.path.exists(cpath):
            continue
        data = list(csv.reader(open(cpath, encoding="utf-8-sig", newline="")))
        if len(data) < 2:
            continue
        head = [c for c in data[0][1:] if c.strip()]
        last, nlast = last_filled(data)
        gran = ("季度" if re.match(r"^\d{4}Q[1-4]$", str(last))
                else "月度" if re.match(r"^\d{4}-\d{2}$", str(last)) else "年度")
        ch, up, note = UPSTREAM.get(key, ("", "", ""))
        cov = nlast / max(1, len(data) - 1)
        rows.append((key, title, head[0], last, gran, len(head),
                     "%d/%d" % (nlast, len(data) - 1), ch, up, note))

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("# 竞速视频数据刷新报告（2026-09-06）\n\n")
        f.write("目标：把数据补到最新（2026），并在上游允许时把年度细化到季度/月度。\n\n")
        f.write("| 题材 | 标题 | 起 | 止 | 粒度 | 列数 | 末列覆盖 | 通道 | 上游最新 | 备注 |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|\n")
        for r in rows:
            f.write("| `%s` | %s | %s | **%s** | %s | %d | %s | %s | %s | %s |\n"
                    % (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9]))
        f.write("\n## 说明\n\n")
        f.write("- **末列覆盖**＝最后一列有值的实体数 / 总实体数。竞速只画 Top N，"
                 "所以判定能否扩年的标准是「上一年 Top-N 实体在新列还有值」，"
                 "而不是全表覆盖率。\n")
        f.write("- **已截**＝上游有该年数据，但 Top-N 命中率不足（<80%），为避免末帧掉柱主动回退。\n")
        f.write("- **上游就到 X**＝数据源本身停在该年，非本流程问题。\n")
        f.write("- ⛔ ＝通道不可用或需人工，本次未更新。\n")
    print("写出", OUT, "共", len(rows), "题材")


if __name__ == "__main__":
    main()
