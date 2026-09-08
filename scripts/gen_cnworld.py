#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""中外对比题材 · 自动生成口播稿 + 发布文案（标题/话题/简介）。

读取 data/cn_world.json（collect_cn_world.py 产出），算出：
  中国(highlight) 起始 vs 最新、反超年份与对象、当前领先幅度、增长倍数，
据此起草「中国逆袭」叙事的口播稿（data/narration.txt）与发布文案
（data/post_meta.json / .txt，小红书风格）。

用法：
  python gen_cnworld.py --workspace <ws>
纯本地计算，无需联网 / LLM；数字来自题材 JSON，发布前请核对。
"""
import argparse, json, os
from datetime import datetime


def fmt(x):
    if abs(x) >= 100 or float(x).is_integer():
        return f"{x:.0f}"
    return f"{x:.1f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', default=os.getcwd())
    a = ap.parse_args()
    ws = os.path.abspath(a.workspace)
    src = os.path.join(ws, 'data', 'cn_world.json')
    if not os.path.exists(src):
        raise SystemExit(f"ERROR: 找不到 {src}，请先跑 collect_cn_world.py")

    data = json.load(open(src, encoding='utf-8'))
    meta = data.get('meta', {})
    years = data['years']
    hl = meta.get('highlight') or '中国'
    unit = meta.get('unit', '')
    title = meta.get('title', '中外对比竞速')
    y0, y1 = years[0], years[-1]
    span = int(''.join(filter(str.isdigit, y1))) - int(''.join(filter(str.isdigit, y0)))

    ents = {it['name']: it['values'] for it in data['industries']}
    def get(name, y):
        return ents.get(name, {}).get(y)

    # 中国起止
    cn0 = get(hl, y0)
    cn1 = get(hl, y1)

    # 每年排名，定位反超
    overtaken = None
    overtake_year = None
    for i in range(len(years)):
        ranked = sorted(data['industries'],
                        key=lambda it: get(it['name'], years[i]) or -1e9, reverse=True)
        if ranked[0]['name'] == hl and i > 0:
            prev_ranked = sorted(data['industries'],
                                 key=lambda it: get(it['name'], years[i - 1]) or -1e9, reverse=True)
            overtaken = prev_ranked[0]['name']
            overtake_year = years[i]
            break

    # 当前排名与领先幅度
    last_ranked = sorted(data['industries'],
                         key=lambda it: get(it['name'], y1) or -1e9, reverse=True)
    cn_rank = next(i for i, it in enumerate(last_ranked) if it['name'] == hl) + 1
    second = last_ranked[1] if len(last_ranked) > 1 else None
    margin = (get(hl, y1) - get(second['name'], y1)) if second else None

    # 增长倍数
    mult = (cn1 / cn0) if (cn0 not in (None, 0)) else None

    # ---------- 口播稿 ----------
    lines = []
    if overtaken and overtake_year:
        lines.append(
            f"从{y0}年到{y1}年，我们把「{title.split('·')[0].strip()}」做成一场中外竞速，"
            f"结局很提气。")
        lines.append(
            f"早年的{y0}年，{hl}只有{fmt(cn0)}{unit}，{overtaken}还遥遥领先；"
            f"到了{overtake_year}年，{hl}完成反超，一路把差距拉开。")
    else:
        lines.append(
            f"从{y0}年到{y1}年，{hl}在「{title.split('·')[0].strip()}」上一路领跑，"
            f"把外国同行越甩越远。")
    if mult and mult >= 2:
        lines.append(
            f"到最新，{hl}达到{fmt(cn1)}{unit}，大约是{y0}年的{int(round(mult))}倍；")
    else:
        lines.append(f"到最新，{hl}达到{fmt(cn1)}{unit}；")
    if second and margin is not None:
        lines.append(
            f"目前高居第{cn_rank}，比第二的{second['name']}还多出{fmt(margin)}{unit}。"
            f"同一个赛道，选对方向、沉下心搞制造，中国这二十年走出了自己的节奏。")
    else:
        lines.append(
            f"目前高居第{cn_rank}。同一个赛道，沉下心搞制造，中国这二十年走出了自己的节奏。")
    narration = "\n".join(lines)

    # ---------- 发布文案 ----------
    titles = [
        f"{hl}用{span}年从跟跑变领跑：一张图看懂中外产业逆袭🏁",
        f"{overtaken+'曾遥遥领先，如今被'+hl+'反超' if overtaken else hl+'一路领跑'}——这张榜太真实",
        f"数据不会骗人：{hl}在「{title.split('·')[0].strip()}」上把外国甩开多远",
        f"大国重器｜{hl}{fmt(cn1)}{unit}登顶，当年想都不敢想",
        f"同样是{title.split('·')[0].strip()}，{hl}和外国差出几个身位？",
    ]

    # 话题标签（按题材关键词匹配 + 通用）
    kw_map = {
        '汽车': ['#中国汽车', '#新能源车'],
        '光伏': ['#中国光伏', '#新能源'],
        '盾构机': ['#盾构机', '#中国基建', '#工程机械'],
        '植树': ['#植树造林', '#绿水青山', '#生态中国'],
        '造林': ['#植树造林', '#绿水青山', '#生态中国'],
        '造船': ['#中国造船', '#造船强国'],
    }
    topics = []
    for k, v in kw_map.items():
        if k in title:
            topics += v
            break
    topics += ['#中国制造', '#中国智造', '#工业明珠', '#大国重器', '#数据可视化']

    takeaway = (
        f"{hl}从{fmt(cn0)}{unit}做到{fmt(cn1)}{unit}"
        + (f"，约{int(round(mult))}倍增长" if mult and mult >= 2 else "")
        + (f"，{overtake_year}年反超{overtaken}" if overtaken else "")
        + "。视频用金色标记中国，动态竞速一目了然👇"
    )
    intro = (
        f"用公开数据跑一场「{title}」的中外竞速🏁 从{y0}到{y1}，"
        f"{hl}从{fmt(cn0)}{unit}干到{fmt(cn1)}{unit}，"
        + (f"在{overtake_year}年反超{overtaken}、一路登顶。" if overtaken else "一路领跑。")
        + f"\n\n{takeaway}"
    )

    meta_out = {
        'platform': 'xhs',
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'kind': 'cn_vs_world',
        'titles': titles,
        'topics': topics,
        'intro': intro,
        'stats': {
            'highlight': hl, 'first': fmt(cn0), 'last': fmt(cn1), 'unit': unit,
            'overtaken': overtaken, 'overtake_year': overtake_year,
            'growth_x': (round(mult, 1) if mult else None),
        },
    }

    nar_path = os.path.join(ws, 'data', 'narration.txt')
    jpath = os.path.join(ws, 'data', 'post_meta.json')
    tpath = os.path.join(ws, 'data', 'post_meta.txt')
    with open(nar_path, 'w', encoding='utf-8') as f:
        f.write(narration + "\n")
    with open(jpath, 'w', encoding='utf-8') as f:
        json.dump(meta_out, f, ensure_ascii=False, indent=2)
    with open(tpath, 'w', encoding='utf-8') as f:
        f.write(f"平台：小红书  |  生成于 {meta_out['generated_at']}\n")
        f.write(f"题材：{title}\n")
        f.write("=" * 40 + "\n\n")
        f.write("【口播稿】\n" + narration + "\n\n")
        f.write("【标题候选】（挑一个用）\n")
        for i, t in enumerate(titles, 1):
            f.write(f"{i}. {t}\n")
        f.write("\n【话题 / 标签】\n")
        f.write("  ".join(topics) + "\n\n")
        f.write("【简介】\n")
        f.write(intro + "\n")

    print("wrote", nar_path)
    print("wrote", jpath, "/", tpath)
    print("--- 口播稿 ---\n" + narration)
    print("--- 简介 ---\n" + intro)


if __name__ == '__main__':
    main()
