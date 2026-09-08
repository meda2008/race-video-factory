# -*- coding: utf-8 -*-
"""把 data/topic_<slug>.json（years/industries/meta 结构）转成 csv 适配器能吃的宽表 CSV，
并生成补充 registry topics_registry_extra.json，用于补齐 batch_rerender 漏掉的两支
（marriage_rate 结婚率、world_top10_houseprice 全球房价最贵城市）。
"""
import json, os, csv

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DIR = os.path.join(WS, "data", "topics_csv")
os.makedirs(CSV_DIR, exist_ok=True)

SLUGS = {
    "marriage_rate": {"theme": "humanity",
                       "bg_prompt": "高级社会人口可视化背景，温润米金至近黑竖向渐变，抽象的家庭与同心圆光纹，电影感，四周加重暗角，画面干净无文字，适合结婚率走势竞速衬底，克制温情"},
    "world_top10_houseprice": {"theme": "finance",
                               "bg_prompt": "高级房地产可视化背景，深邃金棕至近黑竖向渐变，抽象的城市天际线剪影与暖调光斑，电影感，四周加重暗角，画面干净无文字，适合全球房价排行竞速衬底，奢华克制"},
}

entries = []
for slug, extra in SLUGS.items():
    d = json.load(open(os.path.join(WS, "data", f"topic_{slug}.json"), encoding="utf-8"))
    years = [str(y) for y in d["years"]]
    inds = d["industries"]
    meta = d.get("meta", {})

    # 写 CSV：首行 name|code,year...；每行 实体,值...
    csv_path = os.path.join(CSV_DIR, f"{slug}.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name|code"] + years)
        for it in inds:
            name = it.get("name", "")
            code = it.get("code", "")
            row = [f"{name}|{code}" if code else name]
            for y in years:
                v = it.get("values", {}).get(y)
                row.append("" if v is None else v)
            w.writerow(row)
    print(f"[csv] wrote {csv_path} ({len(inds)} entities x {len(years)} years)")

    entry = {
        "key": slug,
        "source": "csv",
        "params": {
            "path": f"data/topics_csv/{slug}.csv",
            "title": meta.get("title", slug),
            "subtitle": meta.get("subtitle", ""),
            "unit": meta.get("unit", ""),
            "mode": meta.get("mode", "value"),
            "decimals": meta.get("decimals", 2),
            "highlight": meta.get("highlight"),
            "legend": meta.get("legend", ""),
            "source": meta.get("src", ""),
            "theme": extra["theme"],
            "bg_prompt": extra["bg_prompt"],
        },
    }
    entries.append(entry)

reg_path = os.path.join(WS, "topics_registry_extra.json")
# 注意：run.py 的 topic_config 要求 registry 是带 "topics" 键的 dict，不是顶层 list！
with open(reg_path, "w", encoding="utf-8") as f:
    json.dump({"topics": entries}, f, ensure_ascii=False, indent=2)
print(f"[registry] wrote {reg_path} ({len(entries)} entries)")
