#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""根据累计收益 JSON 自动生成发布用元数据：标题(多候选)、话题、简介。

在视频成片之后调用，产出可直接用于小红书 / 公众号发布的文案草稿。

用法：
  python gen_meta.py --workspace <ws> [--platform xhs]
  python gen_meta.py --workspace <ws> --platform wechat

读取 <ws>/data/sw_industry_cumul.json
写出 <ws>/data/post_meta.json  (机读：titles / topics / intro / stats)
      <ws>/data/post_meta.txt  (人读草稿，可手改后再发布)

platform:
  xhs    -> 小红书风格（emoji 钩子 + #话题 + 软性引导）
  wechat -> 公众号风格（克制干货，无 emoji 钩子）

纯本地模板生成，无需联网 / LLM；数据来自累计 JSON，数字是真的，文案是模板的，
可按需手改或用 khazix-writer / 猫笔刀写作风格 等 skill 二次润色。
"""
import argparse, json, os
from datetime import datetime

PLATFORMS = ('xhs', 'wechat')


def fmt_pct(x):
    return ("+" if x >= 0 else "") + f"{x:.0f}"


def fmt_abs(x):
    """只取绝对值整数，配合「涨/跌」等动词使用，避免 + / - 与动词重复。"""
    return f"{abs(x):.0f}"


def compute_stats(data):
    years = data['years']
    labels = data.get('year_labels', {})
    first, last = years[0], years[-1]
    last_label = labels.get(last, last)

    rows = []
    for it in data['industries']:
        v = it['values'].get(last)
        if v is None:
            continue
        rows.append((it['name'], v))
    rows.sort(key=lambda x: x[1], reverse=True)

    top3 = rows[:3]
    bottom3 = rows[-3:][::-1]

    # 相邻两年累计差的最大跳变
    best = None
    for it in data['industries']:
        vals = it['values']
        for i in range(1, len(years)):
            y0, y1 = years[i - 1], years[i]
            v0, v1 = vals.get(y0), vals.get(y1)
            if v0 is None or v1 is None:
                continue
            j = v1 - v0
            if best is None or abs(j) > abs(best[2]):
                best = (it['name'], labels.get(y1, y1), j)

    return {
        'first': first,
        'last': last,
        'last_label': last_label,
        'span': int(''.join(filter(str.isdigit, last))) - int(''.join(filter(str.isdigit, first))),
        'n': len(rows),
        'top3': top3,
        'bottom3': bottom3,
        'best_jump': best,
        'lead': top3[0],
        'tail': bottom3[0],
    }


def gen_xhs(s):
    sy, ly = s['first'], s['last_label']
    span = s['span']
    lead, tail = s['lead'], s['tail']
    la, ta = fmt_abs(lead[1]), fmt_abs(tail[1])
    titles = [
        f"同样是A股，{sy}年至今差距有多大？这张行业收益榜我直接存了📊",
        f"申万{s['n']}个行业{sy}至今累计收益：{lead[0]}涨{la}%，{tail[0]}却跌{ta}%",
        f"选对赛道有多重要？一张动态图看懂A股这几年的分化🏁",
        f"老股民私藏｜{lead[0]}累计{la}%，{tail[0]}深跌{ta}%，差距太真实",
        f"{span}年长跑谁在领跑A股？{lead[0]}用{la}%告诉你答案",
    ]
    topics = [
        "#A股", "#申万一级行业", "#复利", "#行业轮动", "#理财干货",
        "#数据可视化", "#投资理财", "#我的炒股日记", "#股市复盘", "#长期投资",
    ]
    jump = s['best_jump']
    jump_line = ""
    if jump and abs(jump[2]) >= 30:
        jump_line = f"{jump[0]}在{jump[1]}一年累计跳升约{abs(jump[2]):.0f}个百分点，直接把差距拉开。\n\n"
    intro = (
        f"用申万一级行业指数跑一场从{sy}年至今的收益竞速🏁 {span}年下来，"
        f"{lead[0]}累计涨了{la}%，而{tail[0]}跌去{ta}%，选对赛道和选错赛道，结局天差地别。\n\n"
        f"{jump_line}"
        f"科技线（通信、电子、有色）整体压过消费线（食品饮料、美容护理、地产），"
        f"这份动态榜单建议收藏对照。视频用红涨绿跌的竞速动画呈现，一眼看清谁在领跑👇"
    )
    return titles, topics, intro


def gen_wechat(s):
    sy, ly = s['first'], s['last_label']
    span = s['span']
    lead, tail = s['lead'], s['tail']
    la, ta = fmt_abs(lead[1]), fmt_abs(tail[1])
    titles = [
        f"{sy}年至今，申万一级行业累计收益全景",
        f"{lead[0]}领跑、{tail[0]}垫底：一张图看懂A股行业分化",
        f"近{span}年A股行业收益榜：科技线全面压过消费线",
    ]
    topics = [
        "#A股", "#申万一级行业", "#行业轮动", "#复利投资", "#理财干货",
    ]
    intro = (
        f"本文用申万一级行业指数，呈现{sy}年至今的累计收益竞速。"
        f"{lead[0]}以{la}%领跑全场，{tail[0]}累计{ta}%垫底，行业分化显著。"
        f"科技板块（通信、电子、有色金属）整体强于消费板块（食品饮料、美容护理、房地产），"
        f"供投资者对照参考。"
    )
    return titles, topics, intro


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', default=os.getcwd())
    ap.add_argument('--platform', choices=PLATFORMS, default='xhs')
    a = ap.parse_args()
    ws = os.path.abspath(a.workspace)
    src = os.path.join(ws, 'data', 'sw_industry_cumul.json')
    if not os.path.exists(src):
        raise SystemExit(f"ERROR: 找不到 {src}，请先跑 build_cumul.py")

    data = json.load(open(src, encoding='utf-8'))
    s = compute_stats(data)
    titles, topics, intro = (gen_xhs(s) if a.platform == 'xhs' else gen_wechat(s))

    meta = {
        'platform': a.platform,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'titles': titles,
        'topics': topics,
        'intro': intro,
        'stats': {
            'range': f"{s['first']}→{s['last_label']}",
            'n_industries': s['n'],
            'lead': {'name': s['lead'][0], 'cumul': s['lead'][1]},
            'tail': {'name': s['tail'][0], 'cumul': s['tail'][1]},
            'best_jump': (s['best_jump'][0] if s['best_jump'] else None),
        },
    }

    jpath = os.path.join(ws, 'data', 'post_meta.json')
    tpath = os.path.join(ws, 'data', 'post_meta.txt')
    with open(jpath, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    with open(tpath, 'w', encoding='utf-8') as f:
        f.write(f"平台：{('小红书' if a.platform=='xhs' else '公众号')}  |  生成于 {meta['generated_at']}\n")
        f.write(f"数据区间：{meta['stats']['range']}（{s['n']}个申万一级行业）\n")
        f.write("=" * 40 + "\n\n")
        f.write("【标题候选】（挑一个用）\n")
        for i, t in enumerate(titles, 1):
            f.write(f"{i}. {t}\n")
        f.write("\n【话题 / 标签】\n")
        f.write("  ".join(topics) + "\n\n")
        f.write("【简介】\n")
        f.write(intro + "\n")

    print("wrote", jpath)
    print("wrote", tpath)
    print("--- preview ---")
    print("标题候选：")
    for i, t in enumerate(titles, 1):
        print(f"  {i}. {t}")
    print("话题：", "  ".join(topics))
    print("简介：")
    print(intro)


if __name__ == '__main__':
    main()
