#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""方案 B：AI 生图打底 + 数据叠加。

把归一化数据 JSON（同 skill 数据契约：years / year_labels / industries[{name,code,values{年:数}}]）
渲染成一支竖屏(1080x1624)信息图视频：
  - 调用 baoyu-image2 生成艺术背景（从 IMAGE2_API_KEY / IMAGE2_BASE_URL 环境变量或
    ~/.workbuddy/models.json 解析 key 与 base_url；不强制传 --model，让 generate_image2.py
    自动走该账号可用的 /images/generations 或 /v1/responses 路径）；
    未配置 key 或 --no-ai 时，回退 Pillow 深色渐变占位背景（整条流水线可无 key 跑通验证）。
  - 用 Pillow 在 1080x1624 设计层叠一张精确的排名数据表（申万 31 行 / 任意 N 行均可）。
  - ffmpeg 对合成图做缓慢推镜(Ken Burns)成片，叠加 BGM（可选配音）。

数据着色遵循 A股惯例：涨/正 = 红，跌/负 = 绿；榜首一行加金色高亮。

用法：
  python imgtable.py --workspace <ws> [--src data/sw_industry_cumul.json]
                     [--bg-prompt "..."] [--no-ai] [--voice] [--duration 12]
                     [--unit %] [--title "自定义标题"]
"""
import argparse, os, sys, json, subprocess, textwrap

FF = "C:/ProgramData/chocolatey/bin/ffmpeg"
FFPROBE = "C:/ProgramData/chocolatey/bin/ffprobe"
BAOYU = "C:/Users/medam/.workbuddy/skills/baoyu-image2/scripts/generate_image2.py"
PY = sys.executable

FONT_BOLD = "C:/Windows/Fonts/simhei.ttf"
FONT_REG = "C:/Windows/Fonts/msyh.ttc"

CW, CH = 1080, 1624                     # 成品尺寸
SRC_SCALE = 1.5                         # 背景放大倍率（给慢推留余量）
BW, BH = int(CW * SRC_SCALE), int(CH * SRC_SCALE)   # 1620 x 2436
RED = (255, 91, 91)
GREEN = (70, 209, 127)
GOLD = (255, 209, 102)
LIGHT = (240, 244, 248)
MUTE = (159, 179, 200)
HEAD = (207, 227, 255)


def run(cmd):
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


# ---------- 数据 ----------
def load_rows(src, unit):
    d = json.load(open(src, encoding="utf-8"))
    years = d.get("years", [])
    if not years:
        raise SystemExit("ERROR: JSON 缺少 years")
    latest = years[-1]
    items = []
    for it in d.get("industries", []):
        vals = it.get("values", {})
        v = vals.get(latest)
        if v is None:
            # 兼容「单值实体」：把某一年当成一行时，用其唯一数值兜底
            if len(vals) == 1:
                v = next(iter(vals.values()))
            else:
                continue
        items.append((it.get("name", "?"), float(v), it.get("code", "")))
    items.sort(key=lambda x: x[1], reverse=True)
    meta = {
        "latest": latest,
        "latest_label": d.get("year_labels", {}).get(latest, latest),
        "first_label": d.get("year_labels", {}).get(years[0], years[0]),
        "unit": unit,
        "n": len(items),
    }
    return items, meta


# ---------- 背景 ----------
def make_placeholder(out_path):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (BW, BH), (8, 12, 22))
    d = ImageDraw.Draw(img)
    # 斜向深色渐变 + 暗角，纯做衬底
    for y in range(BH):
        t = y / BH
        r = int(8 + (18 - 8) * t)
        g = int(12 + (26 - 12) * t)
        b = int(22 + (40 - 22) * t)
        d.line([(0, y), (BW, y)], fill=(r, g, b))
    # 简单光点
    import random
    random.seed(7)
    for _ in range(120):
        x = random.randint(0, BW)
        y = random.randint(0, BH)
        r = random.randint(1, 3)
        a = random.randint(20, 70)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(120, 150, 200, a)[:3])
    img.save(out_path)
    print("[bg] placeholder gradient ->", out_path)


def _workbuddy_image_key_present():
    """key 来源：优先进程环境变量 IMAGE2_API_KEY / OPENAI_API_KEY，
    其次回退 ~/.workbuddy/models.json 里已配置的 apiKey。"""
    if os.environ.get("IMAGE2_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        return True
    p = os.path.join(os.path.expanduser("~"), ".workbuddy", "models.json")
    if os.path.exists(p):
        try:
            data = json.load(open(p, encoding="utf-8-sig"))
        except Exception:
            return False
        models = data if isinstance(data, list) else [data]
        return any(isinstance(m, dict) and m.get("apiKey") for m in models)
    return False


def gen_background(ws, prompt, out_path, no_ai):
    if no_ai or not _workbuddy_image_key_present():
        reason = "--no-ai" if no_ai else "未检测到 IMAGE2_API_KEY（models.json 亦无）"
        print(f"[bg] {reason}，使用占位背景（配置 key 后重跑可换 gpt-image-2 生图）")
        make_placeholder(out_path)
        return "placeholder"
    try:
        env = dict(os.environ)
        # 注意：不要在这里传 --model gpt-image-2。
        # baoyu-image2 的 /v1/responses 路径用的是「对话模型 + image_generation 工具」，
        # 本账号直接 model=gpt-image-2 会 502。不传 --model 时，resolve_config 自动
        # 回退到 models.json 里的对话模型（gpt-5.6-sol）作为 responses 路径的 chat_model，
        # 而 /images/generations 兜底路径仍默认用 gpt-image-2，符合设计。
        # 仅依赖进程环境变量 IMAGE2_API_KEY / IMAGE2_BASE_URL（无则读 models.json）。
        run([PY, BAOYU, "--prompt", prompt, "--output", out_path,
             "--size", f"{BW}x{BH}"])
        if os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
            print("[bg] gpt-image-2 生成成功 ->", out_path)
            return "ai"
    except Exception as e:
        print("[bg] gpt-image-2 调用失败，回退占位背景：", repr(e))
    make_placeholder(out_path)
    return "placeholder"


# ---------- 表格叠加 ----------
def composite(design_path, bg_path, rows, meta, label):
    from PIL import Image, ImageDraw, ImageFont
    bg = Image.open(bg_path).convert("RGB")
    bw, bh = bg.size
    # cover 缩放到 BWxBH
    scale = max(BW / bw, BH / bh)
    nb = bg.resize((int(bw * scale) + 1, int(bh * scale) + 1))
    left = (nb.width - BW) // 2
    top = (nb.height - BH) // 2
    base = nb.crop((left, top, left + BW, top + BH)).convert("RGBA")

    des = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(des)

    # 面板
    pad = 36
    d.rounded_rectangle([pad, 110, CW - pad, CH - 70], radius=22,
                        fill=(9, 13, 22, 178))
    d.rounded_rectangle([pad, 110, CW - pad, CH - 70], radius=22,
                        outline=(120, 160, 220, 90), width=2)

    fb = ImageFont.truetype(FONT_BOLD, 50)
    fr = ImageFont.truetype(FONT_REG, 28)
    fh = ImageFont.truetype(FONT_BOLD, 32)
    fk = ImageFont.truetype(FONT_BOLD, 30)
    fn = ImageFont.truetype(FONT_REG, 32)
    fv = ImageFont.truetype(FONT_REG, 34)

    # 标题
    d.text((CW // 2, 158), label, font=fb, fill=LIGHT, anchor="mm")
    if meta["unit"] == "%":
        sub = f"{meta['first_label']} → {meta['latest_label']}  ·  排名榜  ·  红涨绿跌"
    else:
        sub = f"{meta['first_label']} → {meta['latest_label']}  ·  排名榜  ·  数值越高越靠前"
    d.text((CW // 2, 200), sub, font=fr, fill=MUTE, anchor="mm")

    # 表头
    x_rank, x_name, x_val = 96, 220, CW - 96
    y_head = 250
    d.text((x_rank, y_head), "排名", font=fh, fill=HEAD, anchor="mm")
    d.text((x_name, y_head), "名称", font=fh, fill=HEAD, anchor="lm")
    unit = meta["unit"]
    d.text((x_val, y_head), f"数值{('(' + unit + ')') if unit else ''}",
           font=fh, fill=HEAD, anchor="rm")
    d.line([(pad + 24, y_head + 26), (CW - pad - 24, y_head + 26)],
           fill=(120, 160, 220, 110), width=2)

    # 表体（行数少时限制行高并垂直居中，避免 giant row）
    top = y_head + 44
    bottom = CH - 110
    body_h = bottom - top
    n = len(rows)
    max_row_h = 140
    row_h = min(max_row_h, body_h / max(n, 1))
    table_h = row_h * n
    top = top + (body_h - table_h) / 2
    for i, (name, val, code) in enumerate(rows):
        y = top + i * row_h
        yc = y + row_h / 2
        # 隔行底色
        if i % 2 == 0:
            d.rectangle([pad + 16, y + 2, CW - pad - 16, y + row_h - 2],
                        fill=(255, 255, 255, 14))
        # 榜首金色高亮
        if i == 0:
            d.rectangle([pad + 16, y + 2, pad + 26, y + row_h - 2], fill=GOLD)
            d.text((x_rank, yc), "1", font=fk, fill=GOLD, anchor="mm")
        else:
            d.text((x_rank, yc), str(i + 1), font=fk, fill=MUTE, anchor="mm")
        # 名称（过长省略）
        nm = name if len(name) <= 9 else name[:8] + "…"
        d.text((x_name, yc), nm, font=fn, fill=LIGHT, anchor="lm")
        # 数值
        if unit == "%":
            vs = f"{val:+.2f}{unit}"
        elif unit:
            vs = f"{val:.2f} {unit}"
        else:
            vs = f"{val:.2f}"
        col = RED if val >= 0 else GREEN
        if i == 0:
            col = GOLD
        d.text((x_val, yc), vs, font=fv, fill=col, anchor="rm")

    # 脚注
    d.text((CW // 2, CH - 44),
           "数据来源：AKShare / 题材库  ·  方案 B：AI 生图打底 + 数据叠加",
           font=ImageFont.truetype(FONT_REG, 22), fill=MUTE, anchor="mm")

    # 居中贴到背景的 1080x1624 安全区（慢推不会裁掉表格）
    safe_x = (BW - CW) // 2
    safe_y = (BH - CH) // 2
    base.alpha_composite(des, (safe_x, safe_y))
    base.convert("RGB").save(design_path)
    print("[composite] ->", design_path)


# ---------- 文案 / 元数据 ----------
def fmtv(val, unit):
    if unit == "%":
        return f"{val:+.2f}%"
    return f"{val:.2f}{unit}"


def gen_narration(ws, rows, meta, label):
    top3 = rows[:3]
    bot3 = rows[-3:]
    t = "，".join(f"{nm}（{fmtv(val, meta['unit'])}）" for nm, val, _ in top3)
    b = "，".join(f"{nm}（{fmtv(val, meta['unit'])}）" for nm, val, _ in bot3)
    if meta["unit"] == "%":
        lead = f"累计{top3[0][1]:+.2f}%"
        tail = "完整三十一名排名，请看表格。"
    else:
        lead = f"以{top3[0][1]:.2f}{meta['unit']}居首"
        tail = "完整排名，请看表格。"
    txt = (f"一张图看懂{label}。从{meta['first_label']}到{meta['latest_label']}，"
           f"表现最强的是{top3[0][0]}，{lead}。前三甲分别为：{t}。"
           f"垫底的是：{b}。{tail}")
    p = os.path.join(ws, "data", "imgtable_narration.txt")
    open(p, "w", encoding="utf-8").write(txt)
    print("[narration] ->", p)
    return p


def gen_meta(ws, rows, meta, label, title):
    top = rows[0]
    t0 = title or f"{label}｜一张图看懂"
    titles = [
        t0,
        f"{label}完整榜单（{meta['latest_label']}）",
        f"{top[0]}领跑！{label}排名一览",
    ]
    topics = ["#财经", "#A股", "#数据可视化", "#申万行业", "#一张图看懂"]
    desc = (f"{label}从{meta['first_label']}到{meta['latest_label']}的排名榜，"
            f"榜首{top[0]}（{top[1]:+.2f}{meta['unit']}），共 {meta['n']} 名。"
            f"AI 生图打底 + 精确数据表格叠加。")
    out = {"titles": titles, "topics": topics, "desc": desc,
           "kind": "imgtable", "label": label}
    pj = os.path.join(ws, "data", "imgtable_post_meta.json")
    pt = os.path.join(ws, "data", "imgtable_post_meta.txt")
    json.dump(out, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    with open(pt, "w", encoding="utf-8") as f:
        f.write("标题候选：\n")
        for t in titles:
            f.write(f"  - {t}\n")
        f.write("话题：\n  " + " ".join(topics) + "\n")
        f.write("简介：\n  " + desc + "\n")
    print("[meta] ->", pj)
    return pj


# ---------- 视频 ----------
def build_video(ws, composite_path, dur, vo_path, bgm_path, final):
    silent = os.path.join(ws, "out", "_imgtable_silent.mp4")
    aud = os.path.join(ws, "out", "_imgtable_audio.m4a")
    frames = int(dur * 30)

    run([FF, "-y", "-loop", "1", "-i", composite_path,
         "-vf", (f"zoompan=z='min(zoom+0.0015,1.16)':d={frames}:"
                 f"s={CW}x{CH}:fps=30:"
                 f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"),
         "-t", f"{dur}", "-r", "30",
         # PNG(rgb24) 喂给 libx264 默认会选 yuv444p + High 4:4:4，绝大多数播放器/微信/手机不解码，
         # 必须强制 yuv420p + 标准 High profile，否则生成的视频打不开。
         "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0", silent])

    use_voice = vo_path and os.path.exists(vo_path)
    use_bgm = bgm_path and os.path.exists(bgm_path)

    if use_voice and use_bgm:
        run([FF, "-y", "-i", vo_path, "-stream_loop", "-1", "-i", bgm_path,
             "-filter_complex",
             "[0:a]aresample=44100,volume=1.0[voc];"
             "[1:a]aresample=44100,volume=0.22[bgm];"
             "[bgm][voc]sidechaincompress=threshold=0.06:ratio=3.5:attack=15:release=250[duck];"
             "[voc][duck]amix=inputs=2:duration=longest:normalize=0[out]",
             "-map", "[out]", "-t", f"{dur}", "-ar", "44100", "-c:a", "aac", "-b:a", "192k", aud])
    elif use_voice:
        run([FF, "-y", "-i", vo_path, "-f", "lavfi", "-i", "anoisesrc=pink:d=%.3f:r=44100" % dur,
             "-filter_complex",
             "[0:a]aresample=44100,volume=1.0[voc];"
             "[1:a]aresample=44100,lowpass=f=1200,volume=0.12[bgm];"
             "[voc][bgm]amix=inputs=2:duration=longest:normalize=0[out]",
             "-map", "[out]", "-t", f"{dur}", "-ar", "44100", "-c:a", "aac", "-b:a", "192k", aud])
    elif use_bgm:
        run([FF, "-y", "-stream_loop", "-1", "-i", bgm_path,
             "-filter_complex", "[0:a]aresample=44100,volume=0.22[a]",
             "-map", "[a]", "-t", f"{dur}", "-ar", "44100", "-c:a", "aac", "-b:a", "192k", aud])
    else:
        run([FF, "-y", "-f", "lavfi", "-i", "anoisesrc=pink:d=%.3f:r=44100" % dur,
             "-filter_complex", "lowpass=f=1200,afade=t=in:d=1,afade=t=out:d=2,volume=0.5",
             "-t", f"{dur}", "-c:a", "aac", "-b:a", "128k", aud])

    run([FF, "-y", "-i", silent, "-i", aud, "-c", "copy", "-movflags", "+faststart", final])
    print("[video] DONE ->", final)
    print(subprocess.check_output([FFPROBE, "-v", "error",
          "-show_entries", "format=duration,size",
          "-show_entries", "stream=width,height,codec_name,codec_type,r_frame_rate",
          "-of", "default=noprint_wrappers=1", final]).decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=os.getcwd())
    ap.add_argument("--data", default=None, help="归一化数据 JSON（默认 data/sw_industry_cumul.json）")
    ap.add_argument("--bg-prompt", default=None, help="自定义 gpt-image-2 背景提示词")
    ap.add_argument("--no-ai", action="store_true", help="强制用占位背景（不调 gpt-image-2）")
    ap.add_argument("--voice", action="store_true", help="生成并叠加 AI 配音")
    ap.add_argument("--duration", type=float, default=12.0, help="成片时长(秒)")
    ap.add_argument("--unit", default="%", help="数值单位（默认 %）")
    ap.add_argument("--title", default=None, help="自定义标题/标签（覆盖自动命名）")
    a = ap.parse_args()
    ws = os.path.abspath(a.workspace)
    data = os.path.join(ws, "data")
    out = os.path.join(ws, "out")
    os.makedirs(data, exist_ok=True)
    os.makedirs(out, exist_ok=True)

    src = a.data or os.path.join(data, "sw_industry_cumul.json")
    if not os.path.exists(src):
        raise SystemExit(f"ERROR: 找不到数据 JSON {src}")
    rows, meta = load_rows(src, a.unit)

    # 标签（用于标题/表头）
    stem = os.path.basename(src).replace(".json", "")
    if a.title:
        label = a.title
    elif "cumul" in stem:
        label = "申万一级行业累计收益"
    elif "cn_world" in stem:
        label = "中外产业对比"
    elif "finance" in stem:
        label = "财经主题榜"
    else:
        label = stem

    # 背景
    prompt = a.bg_prompt or (
        "极简财经科技感竖版背景，深蓝近黑渐变，抽象数据流动与细微光点，"
        "电影感，四周暗角，画面干净无文字，适合做数据图表衬底，留白克制")
    bg_path = os.path.join(out, "_imgtable_bg.png")
    gen_background(ws, prompt, bg_path, a.no_ai)

    # 合成（设计层 1080x1624 + 背景）
    composite_path = os.path.join(out, "_imgtable_composite.png")
    composite(composite_path, bg_path, rows, meta, label)

    # 文案 / 元数据
    gen_meta(ws, rows, meta, label, a.title)
    vo_path = None
    if a.voice:
        np = gen_narration(ws, rows, meta, label)
        run([PY, os.path.join(os.path.dirname(__file__), "tts.py"),
             "--workspace", ws, "--src", np,
             "--out", os.path.join(data, "imgtable_voiceover.mp3")])
        vo_path = os.path.join(data, "imgtable_voiceover.mp3")

    # BGM（缓存命中即跳过）
    run([PY, os.path.join(os.path.dirname(__file__), "fetch_bgm.py"), "--workspace", ws])
    bgm_path = os.path.join(data, "bgm", "bgm.mp3")

    # 成片
    final = os.path.join(out, "imgtable.mp4")
    build_video(ws, composite_path, a.duration, vo_path, bgm_path, final)
    print("[done] 成片：", final)


if __name__ == "__main__":
    main()
