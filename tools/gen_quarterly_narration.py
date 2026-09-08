# -*- coding: utf-8 -*-
"""为季度化 4 支 A股题材（profit/loss/revenue/sellexp）按真实季度数据生成口播稿。
数据驱动，不依赖 LLM，确保季度数字准确，风格对齐现有 A股 口播。
- profit/revenue/sellexp：数值均为正，取最大值者为「登顶」。
- loss：数值为带符号净利润（负=亏损）。「亏损王」只排实际亏损者（v<0），
        按亏损额（绝对值）从大到小；盈利者不算亏损王。
用法：python scripts_local/gen_quarterly_narration.py
"""
import json, os, csv

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODES = ["profit", "loss", "revenue", "sellexp"]
UNIT = "亿元"


def fmt(v):
    """亏损模式用：取绝对值（亏损额用正数表述）。"""
    v = abs(v) if v is not None else 0
    if abs(v) >= 100:
        return f"{v:,.0f}"
    return f"{v:,.1f}"


def fmt_signed(v):
    """非亏损模式用：保留正负号（公司转亏时显示为负）。"""
    v = v if v is not None else 0
    if abs(v) >= 100:
        return f"{v:,.0f}"
    return f"{v:,.1f}"


def gen(mode):
    csv_path = os.path.join(WS, "data", "topics_csv", f"ashare_{mode}.csv")
    rows = []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        header = next(r)
        quarters = [h.strip() for h in header[1:]]
        for row in r:
            if not row or not row[0].strip():
                continue
            cell = row[0].strip()
            name = cell.split("|", 1)[0].strip() if "|" in cell else cell
            vals = {}
            for i, q in enumerate(quarters):
                raw = row[i + 1].strip() if i + 1 < len(row) else ""
                vals[q] = float(raw) if raw not in ("", None) else 0.0
            rows.append((name, vals))
    if not rows or len(quarters) < 2:
        print(f"[{mode}] 数据不足，跳过")
        return

    is_loss = (mode == "loss")
    start, end = quarters[0], quarters[-1]

    # 取「参与排名」的值：亏损模式只看实际亏损者(亏损额>0，已转存为正幅度)，其它模式看全部
    def ranked(q):
        out = []
        for n, v in rows:
            x = v.get(q, 0)
            if is_loss:
                if x > 0:
                    out.append((n, x))
            else:
                out.append((n, x))
        return out

    end_r = sorted(ranked(end), key=lambda t: t[1], reverse=True)
    start_r = sorted(ranked(start), key=lambda t: t[1], reverse=True)

    if not end_r:
        print(f"[{mode}] 末季无有效排名数据，跳过")
        return

    end_leader, end_val = end_r[0]
    last_name, last_val = end_r[-1]
    start_leader = start_r[0][0] if start_r else end_leader
    start_val = start_r[0][1] if start_r else 0.0

    # mover = 首季→末季 绝对变化最大（全局）
    best, best_delta = None, -1
    for n, v in rows:
        d = abs(v.get(end, 0) - v.get(start, 0))
        if d > best_delta:
            best_delta, best = d, n
    mover = best
    gap = abs(end_val - last_val)

    lines = [f"从{start}到{end}，我们用动态榜单跑了一场排位竞速。"]
    if is_loss:
        lines.append(f"到了{end}，{end_leader}以{fmt(end_val)}亿元亏损，坐上了「亏损王」的位子。")
    else:
        lines.append(f"到了{end}，{end_leader}以{fmt_signed(end_val)}{UNIT}登顶。")

    if start_leader != end_leader:
        if is_loss:
            lines.append(f"反观{start_leader}，{start}还是以{fmt(start_val)}亿元亏损领跑，到{end}已被{end_leader}反超。")
        else:
            sv = next((v.get(start, 0) for n, v in rows if n == start_leader), 0)
            lines.append(f"反观{start_leader}，{start}还以{fmt_signed(sv)}{UNIT}排在第一，到{end}已跌出榜首——掉得最狠。")

    if is_loss:
        lines.append(f"而{last_name}以{fmt(last_val)}亿元亏损排在最后。")
    else:
        lines.append(f"而{last_name}以{fmt_signed(last_val)}{UNIT}排在最后。")

    lines.append(
        f"其中{mover}从{start}到{end}变化最大，绝对值累计约{fmt(best_delta)}{UNIT}，"
        f"把分化彻底坐实——头尾之间，已经隔出{fmt(gap)}{UNIT}的鸿沟。"
    )

    text = "\n".join(lines)
    out = os.path.join(WS, "data", f"topic_ashare_{mode}_narration.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[{mode}] 口播稿 -> {out}")
    print("   ", text.replace("\n", " ")[:200])


if __name__ == "__main__":
    for m in MODES:
        gen(m)
