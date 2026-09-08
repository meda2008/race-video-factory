#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""根据累计收益 JSON 自动起草猫笔刀式中文口播稿（data/narration.txt）。

用法：
  python gen_narration.py --workspace <ws>
读取 <ws>/data/sw_industry_cumul.json（末年=最新累计）
写出 <ws>/data/narration.txt（草稿，可手动润色后再跑 tts.py）

逻辑：取累计涨幅前三/后三、找出单年最大跳变年份，套入财经口播模板。
      纯本地计算，无需联网 / LLM。
"""
import argparse, json, os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', default=os.getcwd())
    a = ap.parse_args()
    ws = os.path.abspath(a.workspace)
    src = os.path.join(ws, 'data', 'sw_industry_cumul.json')
    if not os.path.exists(src):
        raise SystemExit(f"ERROR: 找不到 {src}，请先跑 build_cumul.py")
    data = json.load(open(src, encoding='utf-8'))
    years = data['years']
    last = years[-1]
    latest = data.get('latest_date', '')

    rows = []
    for it in data['industries']:
        v = it['values'].get(last)
        if v is None:
            continue
        rows.append((it['name'], v))
    rows.sort(key=lambda x: x[1], reverse=True)

    top3 = rows[:3]
    bottom3 = rows[-3:][::-1]

    # 单年最大跳变（相邻两年累计差）
    best_jump = None
    for it in data['industries']:
        vals = it['values']
        for i in range(1, len(years)):
            y0, y1 = years[i - 1], years[i]
            v0, v1 = vals.get(y0), vals.get(y1)
            if v0 is None or v1 is None:
                continue
            jump = v1 - v0
            if best_jump is None or abs(jump) > abs(best_jump[1]):
                best_jump = (it['name'], y1, jump)

    def pct(x):
        return ("+" if x >= 0 else "") + f"{x:.0f}"

    lead = top3[0]
    lines = []
    lines.append(
        f"从{years[0]}年到今天，拿申万一级行业指数跑一场收益竞速，"
        f"几年下来，差距大得惊人。")
    if best_jump and abs(best_jump[2]) >= 30:
        lines.append(
            f"到了{best_jump[1]}年，剧情最猛——{best_jump[0]}一年累计跳升约"
            f"{abs(best_jump[2]):.0f}个百分点，把差距彻底拉开。")
    lines.append(
        f"到最新，{lead[0]}以{pct(lead[1])}%的累计涨幅领跑全场；"
        f"而{bottom3[0][0]}累计{pct(bottom3[0][1])}%，"
        f"{bottom3[-1][0]}同样深跌{pct(bottom3[-1][1])}%，一路向南。")
    lines.append(
        "同一个A股，选对行业天差地别——科技线全面压过消费线，"
        "这份榜单，值得每个投资者收藏对照。")

    text = "\n".join(lines)
    out = os.path.join(ws, 'data', 'narration.txt')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(text + "\n")
    print("wrote", out)
    print("--- draft ---")
    print(text)


if __name__ == '__main__':
    main()
