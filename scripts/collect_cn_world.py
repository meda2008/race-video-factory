#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""中外对比题材采集：把 topics/cn_vs_world/<题材>.json 归一化为 race 兼容的 data/cn_world.json。

用法：
  python collect_cn_world.py --workspace <ws> --topic 汽车
  python collect_cn_world.py --workspace <ws> --list        # 列出可用题材

题材文件结构（已内置 汽车/光伏/盾构机/植树造林/造船）：
  { title, subtitle, unit, highlight, mode:"value", legend, src,
    years:[...], year_labels:{...}, entities:[ {name, code, values:{年:数}} ] }

归一化后 data/cn_world.json 含：
  years / year_labels / industries(=entities) / meta(展示字段)
build_race.py 会读取 meta 作为标题/单位/高亮等，因此无需改 build_race 调用方式。
"""
import argparse, json, os, glob

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOPICS_DIR = os.path.join(SCRIPT_DIR, 'topics', 'cn_vs_world')


def list_topics():
    files = sorted(glob.glob(os.path.join(TOPICS_DIR, '*.json')))
    out = []
    for fp in files:
        name = os.path.splitext(os.path.basename(fp))[0]
        try:
            d = json.load(open(fp, encoding='utf-8'))
            out.append(f"  - {name}  （{d.get('title','')}）")
        except Exception:
            out.append(f"  - {name}  （无法读取）")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', default=os.getcwd())
    ap.add_argument('--topic', default='汽车')
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args()
    ws = os.path.abspath(a.workspace)

    if a.list:
        print("可用中外对比题材：")
        print("\n".join(list_topics()))
        return

    # 解析题材文件名
    name = a.topic
    if not name.endswith('.json'):
        name += '.json'
    src = os.path.join(TOPICS_DIR, name)
    if not os.path.exists(src):
        print(f"ERROR: 找不到题材 {a.topic}（{src}）")
        print("可用题材：")
        print("\n".join(list_topics()))
        raise SystemExit(1)

    d = json.load(open(src, encoding='utf-8'))
    years = d['years']
    ylabels = d.get('year_labels', {y: y for y in years})
    industries = [
        {k: it[k] for k in ('name', 'code', 'values')} for it in d['entities']
    ]
    meta = {
        'title': d.get('title', '中外对比竞速'),
        'subtitle': d.get('subtitle', ''),
        'unit': d.get('unit', ''),
        'highlight': d.get('highlight'),
        'mode': d.get('mode', 'value'),
        'legend': d.get('legend', ''),
        'src': d.get('src', ''),
        'latest_date': years[-1] if years else '',
    }
    out = {
        'years': years,
        'year_labels': ylabels,
        'industries': industries,
        'meta': meta,
    }
    dst = os.path.join(ws, 'data', 'cn_world.json')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("wrote", dst, "topic=", a.topic, "years=", years,
          "entities=", [i['name'] for i in industries])


if __name__ == '__main__':
    main()
