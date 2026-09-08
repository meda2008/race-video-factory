#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从解说稿提取「年份词」出现时刻，生成 race 时间轴 JSON。

用法：
  python gen_timeline.py --src data/topic_x_narration.txt --audio data/voiceover.mp3 --out data/timeline_x.json
可选 --voice / --duration（若不给 audio 则必须给 duration）

原理：按句子切分，用「每句字符数 / 总字符数 × 音频总时长」得到每句起始时刻，再把句中出现的
      4 位年份（19xx/20xx）映射到该句时间区间内的对应位置；一句含多个年份时按字符顺序在该句
      时长内均匀铺开。输出按时间排序的 [{t, year}]。build_race.py --timeline 会把它映射为
      「时间->年份索引」的分段线性函数，使竞速画面与解说提到的年份对齐。

注：edge_tts / Azure 的逐词/逐句时间戳在本环境不可用（Offset 恒为 0），故采用字符比例近似——
      同一音色下语速近似恒定，按字符比例分配时间已能把「说到 2006」与画面推进到 2006 对齐到
      秒级误差以内，远优于默认匀速推进。
"""
import argparse, json, math, os, re, subprocess, sys

FFPROBE = "C:/ProgramData/chocolatey/bin/ffprobe"
EMOJI = re.compile(r'[\U0001F000-\U0001FAFF\u2190-\u21FF\u2300-\u23FF\u25A0-\u25FF\u2B00-\u2BFF\uFE0F]')
SENT_SPLIT = re.compile(r'[。！？!?\n]+')
YEAR = re.compile(r'(?:19|20)\d{2}(?=年)')

# 标签 -> 小数年份的解析：兼容 2015 / 2015Q4 / 2015-12 / 2015/12 / 2015.12
_LBL = re.compile(r'^(\d{4})(?:[-/\.](\d{1,2})|[Qq](\d)|[Mm](\d{1,2})|(\d{2}))?$')
# 锚点数量安全阀门。原 n=min(n,80) 的「防 JSON 过大」理由不成立：无缩进 dumps
# 约 15B/锚点，1200 锚点仅 18KB，而 race.html 本身约 130KB。保留阀门只为防
# CSV 误把数据行当表头导致 N 上万的极端情况。
MAX_ANCHORS = 1200


_NO_DENSIFY = False   # 由 main() 依据 --no-densify 设置


def _pos(label):
    """时间标签 -> 小数年份；无法解析返回 None。

    2015 -> 2015.0；2015Q3 -> 2015.5；2015-07 -> 2015.5
    """
    m = _LBL.match(str(label).strip())
    if not m:
        return None
    y = int(m.group(1))
    for g, div in ((2, 12.0), (3, 4.0), (4, 12.0), (5, 12.0)):
        if m.group(g):
            k = int(m.group(g))
            return y + (k - 1) / div if 1 <= k <= div else None
    return float(y)


def _index_timeline(years, dur, intro=0.7, tail_pad=1.5, inds=None, weight=True):
    """索引空间 + 日历加权：每个数据点一个锚点(idx=i)，时刻按标签的日历距离分配。

    在此基础上叠加「数据变化强度」权重（weight=True 且给了 inds）：
    排名/数值剧烈变化的年份段放慢看清楚，长期一动不动的年份段快进掠过，
    避免「画面推了 40 秒、柱子纹丝不动」。权重由 change_weights() 计算，
    段间快慢差实测 1.4~4.4 倍；全部区间权重相同时自动退化为纯日历加权。

    为什么不用纯索引空间（等间隔）：存在「混合粒度」数据——如 gold_reserves 的
    1950Q4…1956Q4 实为年度数据点（7 年 7 个点）挂季度标签，1957Q1 起才是真季度。
    纯索引空间会把这 7 年压成全程的 7/284；日历加权在此退化回「每年等时」，与旧
    _even_timeline 行为一致。四种粒度下均退化正确：
      年度连续   -> 等时推进（与旧行为逐点相同）
      真季度     -> 每季一个锚点（旧行为停每年末季度，属跳帧，本次顺带修正）
      混合粒度   -> 日历等时（与旧行为几乎一致）
      月度       -> 每月一个锚点（旧行为只生成年度锚点，首尾年速度失真）
    """
    n = len(years)
    if n < 2:
        return []
    pos = [_pos(x) for x in years]
    if any(p is None for p in pos) or any(pos[i + 1] <= pos[i] for i in range(n - 1)):
        # 解析失败或非单调（如自定义标签）-> 退化等间隔
        pos = [float(i) for i in range(n)]
    span = max(0.1, dur - tail_pad - intro)
    # 日历距离（每相邻两点一段）
    seg = [max(1e-6, pos[i + 1] - pos[i]) for i in range(n - 1)]
    used_w = False
    if weight and inds:
        try:
            w = change_weights(years, inds)
            if len(w) == n - 1:
                seg = [seg[i] * w[i] for i in range(n - 1)]
                used_w = True
        except Exception:
            used_w = False
    if used_w:
        print('[gen_timeline] 叠加数据变化强度权重（不动段快进 / 剧变段放慢）')
    tot = sum(seg) or 1.0
    # 累计曲线 -> 锚点时刻
    cum = [0.0]
    for s in seg:
        cum.append(cum[-1] + s)
    step = max(1, math.ceil(n / MAX_ANCHORS))
    idxs = list(range(0, n, step))
    if idxs[-1] != n - 1:
        idxs.append(n - 1)          # 保证末锚点精确落在 N-1
    return [(round(intro + span * cum[i] / tot, 3), i) for i in idxs]


def _year_values(inds, years):
    """返回 {年索引: [各实体当年值]}，兼容 values 为 dict({年:值}) 或 list。"""
    rows = []
    for i, y in enumerate(years):
        row = []
        for it in inds:
            if not isinstance(it, dict):
                continue
            v = it.get('values')
            if isinstance(v, dict):
                v = v.get(str(y))
            elif isinstance(v, (list, tuple)):
                v = v[i] if i < len(v) else None
            row.append(v if isinstance(v, (int, float)) else 0.0)
        rows.append(row)
    return rows


def _rank_of(row):
    """名次向量：值越大名次越小（0=第一）。相同值给相同名次。"""
    order = sorted(range(len(row)), key=lambda k: -row[k])
    r = [0] * len(row)
    prev = None
    for pos, k in enumerate(order):
        if prev is not None and row[k] == prev:
            r[k] = r[order[pos - 1]]
        else:
            r[k] = pos
        prev = row[k]
    return r


def change_weights(years, inds):
    """相邻年份之间的「变化强度」权重，长度 = len(years)-1。

    权重越大 → 该区间分到的画面时间越多（放慢看清楚）；
    长期零变化的区间权重塌到基线，于是被快进，不再占着时间不动。
    """
    n = len(years)
    if n < 2 or not inds:
        return []
    rows = _year_values(inds, years)
    w = []
    for i in range(n - 1):
        a, b = rows[i], rows[i + 1]
        if not a:
            w.append(1.0)
            continue
        ra, rb = _rank_of(a), _rank_of(b)
        n = max(1, len(a))
        # 名次变动：有多少比例的实体换位（0~1）
        moved = sum(1 for k in range(len(a)) if ra[k] != rb[k]) / n
        # 位移幅度（归一化到 0~1）
        shift = min(1.0, (sum(abs(ra[k] - rb[k]) for k in range(len(a))) / n) / max(1.0, n * 0.5))
        churn = 0.6 * moved + 0.4 * shift
        # 数值变动强度
        ma = sum(abs(x) for x in a) or 1.0
        mb = sum(abs(x) for x in b) or 1.0
        growth = min(1.0, abs(mb - ma) / ma)
        # 基线 0.08：完全不动的区间塌到基线 → 被快进；剧变区间最多约 2.0 → 放慢 20 倍。
        # 实测 20 倍过于跳跃，故对总权重做 0.5 次幂压缩，实际快慢差控制在 4~5 倍。
        w.append((0.08 + churn * 1.10 + growth * 0.80) ** 0.5)
    # 归一化，避免整体权重漂移影响可读性（不影响分配比例）
    return w


def densify(pts, years, inds, min_step=0.05):
    """在每个锚点区间内按变化强度插入中间年份锚点。

    口播锚点自身的时刻**保持不变**（音画同步靠它），只把锚点之间的
    中间年份按「变化强度」重新分配时刻：剧变年份放慢，长期不动的年份快进。
    """
    if not years or len(years) < 3 or not inds:
        return pts
    w = change_weights(years, inds)
    if not w:
        return pts
    out = []
    for k in range(len(pts) - 1):
        t0, i0 = pts[k]
        t1, i1 = pts[k + 1]
        out.append((t0, i0))
        try:
            i0i, i1i = int(i0), int(i1)
        except (TypeError, ValueError):
            continue
        if not (0 <= i0i < i1i < len(years)) or t1 <= t0:
            continue
        # 原本每帧就 <50ms，已经够快，不必再插
        if (t1 - t0) / (i1i - i0i) < min_step:
            continue
        seg = w[i0i:i1i]
        tot = sum(seg) or 1.0
        acc = 0.0
        for j in range(i0i + 1, i1i):
            acc += seg[j - i0i - 1]
            out.append((t0 + (t1 - t0) * acc / tot, j))
    out.append(pts[-1])
    return out


def get_duration(audio):
    if not audio or not os.path.exists(audio):
        return None
    try:
        out = subprocess.check_output(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio]).decode().strip()
        return float(out)
    except Exception as e:
        print("warn: ffprobe 取时长失败:", e)
        return None


def _even_timeline(first_year, last_year, dur, intro=0.7, tail_pad=1.5):
    """全数据年份均匀连续时间轴：每年等时推进，杜绝长段冻结 / 跨年压秒跳变。

    用于「口播锚点稀疏」退化场景：解说稿只提到极少数年份时，按年份词对齐会把
    大部分年份压进几秒、末端长期定格，视觉上就是「数据粒度越往后越稀、变化不连续」。
    改为在数据首→末年份区间均匀铺锚点（≈每年一个），竞速画面连续平滑推进。
    """
    if not (first_year and last_year and last_year > first_year):
        return []
    span = max(0.1, dur - tail_pad - intro)
    n = last_year - first_year + 1
    n = min(n, 80)  # 防 JSON 过大
    pts = []
    for i in range(n):
        y = int(round(first_year + i * (last_year - first_year) / (n - 1)))
        t = intro + i * span / (n - 1)
        pts.append((round(t, 3), y))
    # 注：循环末点已落在 (dur - tail_pad, last_year)，故无需再补末端封口锚点。
    return pts


def extract(text, duration, final_year=None, first_year=None, intro=0.7, tail_pad=1.5,
            years=None, inds=None):
    """返回 [(t_seconds, year_or_idx), ...] 按时间排序。

    intro / tail 用于首尾封口，这是「后面不动了」的根治手段：
      末端——前端 yearFloatAt 在 elapsed >= TL[-1][0] 时 clamp 到末锚点，
            若末锚点早于配音尾声，画面会提前定格、口播还在讲后面几年，
            表现就是「速度时快时慢，后面不动了」。
            这里强制补一个 (dur - tail, 末年) 锚点，把推进一直延续到配音尾声。
      首端——render() 在 elapsed < INTRO 时强制 yf = 0（真实起点），
            而 elapsed <= TL[0][0] 时前端返回 TL[0][1]，
            两条规则衔接无空档，故首端无需额外封口。
    final_year 由调用方传入数据真实末年（缺省则取解说稿里出现的最大年份）。

    years 参数：若提供（>=2 个元素的标签列表），优先用「索引空间+日历加权」——
      每个数据点一个锚点，时刻按标签的日历距离分配。这是对原「年份空间」的
      升级：兼容年度/季度/月度/混合粒度，原年空间版本仅在 years 缺失时作为兜底。
    """
    clean = EMOJI.sub('', text)
    clean = re.sub(r'\s+', ' ', clean).strip()
    sentences = []
    pos = 0
    for m in SENT_SPLIT.finditer(clean):
        seg = clean[pos:m.start()].strip()
        if seg:
            sentences.append(seg)
        pos = m.end()
    tail = clean[pos:].strip()
    if tail:
        sentences.append(tail)
    if not sentences:
        return []

    total_chars = sum(len(s) for s in sentences) or 1
    dur = duration or 30.0

    # 新：索引空间 + 日历加权（run.py 总会传 years 进来）
    if years is not None and len(years) >= 2:
        print('[gen_timeline] 索引空间日历加权 %s→%s（%d 点）'
              % (years[0], years[-1], len(years)))
        return _index_timeline(years, dur, intro, tail_pad,
                               inds=inds, weight=not _NO_DENSIFY)

    # 旧：年空间均匀连续时间轴 —— 兜底（仅在独立命令行调用、未传 years 时使用）。
    # 放在解析口播「之前」，故口播里一个年份都没有时(#016 M2占GDP，写的是"从2010到2023"、
    # 2010/2023 后无「年」字) 也能正常产出时间轴，不再因为零锚点而整体失败。
    # 理由：竞速视频首要诉求是「粒度细 + 变化连续」，而「按口播年份词对齐」极度脆弱——
    #   ① 口播无「XXXX年」→ 直接失败无时间轴(#016)；
    #   ② 锚点稀疏 → 大半年份压进几秒、末端冻结(#014 股市市值)；
    #   ③ 末年先在句首提及 → 单调钳制把早年全钳成末年，整段定格(#015 人均GDP)。
    # 改为全数据年份等时推进：每年等时、永不冻结/跳变，粒度即数据真实粒度（最细）。
    # 代价仅是口播与画面年份的秒级错位；叙事型口播("从1995到2025…")完全可接受。
    if first_year and final_year and final_year > first_year:
        print('[gen_timeline] 采用均匀连续时间轴 %d→%d（每年等时推进）'
              % (first_year, final_year))
        return _even_timeline(first_year, final_year, dur, intro, tail_pad)

    points = []
    cum = 0
    for seg in sentences:
        start = cum / total_chars * dur
        sdur = len(seg) / total_chars * dur
        yrs = [int(m.group()) for m in YEAR.finditer(seg)]
        yrs = [y for y in yrs if 1900 <= y <= 2099]
        if not yrs:
            cum += len(seg)
            continue
        if len(yrs) == 1:
            points.append((start + 0.5 * sdur, yrs[0]))
        else:
            for j, y in enumerate(yrs):
                t = start + (j + 0.5) / len(yrs) * sdur
                points.append((t, y))
        cum += len(seg)
    points.sort(key=lambda kv: kv[0])
    if not points:
        return []

    # 注：均匀连续时间轴的默认分支已在函数前部处理（首/末年齐备时直接返回），
    # 此处仅在未传首/末年的独立命令行用法下走「口播年份词对齐」。

    # 防倒退（根治「内容重播」）：口播若在靠后句子回述早年（如「是2010年的一百倍」），
    # 会插入一个早于当前年份的锚点，使屏幕年份计数器从末年倒退回早年再正放，整场视觉重播。
    # 所有题材口播均按时间顺序陈述，故对年份锚点做单调不减钳制——任何早于前一个锚点的年份
    # 都钳制为前一个年份，年份计数器只会前进或停留，绝不倒退。
    mono = []
    prev_y = None
    for t, y in points:
        if prev_y is not None and y < prev_y:
            y = prev_y
        mono.append((t, y))
        prev_y = y
    points = mono

    # 末端封口：补一个贴着配音尾声的锚点，把竞速推进延续到最后，
    # 杜绝「画面提前定格、口播还在讲后面几年」的不同步。
    # 注意：下面有个局部变量 tail（末段文本），参数名必须避开，否则会被遮蔽。
    fy = final_year if final_year is not None else max(y for _, y in points)
    tail_t = max(dur - tail_pad, points[-1][0] + 0.1)
    if tail_t <= dur:
        points.append((tail_t, fy))
        points.sort(key=lambda kv: kv[0])
    return points


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--audio', default=None, help='配音 mp3，用于精确时长（优先）')
    ap.add_argument('--duration', type=float, default=None)
    ap.add_argument('--workspace', default=None,
                    help='兼容 run.py 的统一调用签名（py() 总会带 --workspace），本脚本不使用')
    ap.add_argument('--final-year', type=int, default=None,
                    help='数据真实末年（如 2025）；用于末端封口锚点，缺省则取解说稿最大年份')
    ap.add_argument('--first-year', type=int, default=None,
                    help='数据真实首年（如 1995）；与 --final-year 一起用于稀疏锚点退化保护')
    ap.add_argument('--intro', type=float, default=0.7, help='片头时长（秒），与 build_race 的 INTRO 一致')
    ap.add_argument('--tail', type=float, default=1.5, help='片尾定格时长（秒），与 build_race 的 FINALHOLD 一致')
    ap.add_argument('--data', default=None,
                    help='归一化题材 JSON（data/topic_*.json）。提供则按 years 走「索引空间+日历加权」'
                         '（任意粒度通用，缺此参数时回退年空间仅适用于纯年度/季度标签）')
    ap.add_argument('--no-densify', action='store_true',
                    help='关闭「按数据变化强度重排」（不动的年份段就不再快进）')
    a = ap.parse_args()
    text = open(a.src, encoding='utf-8').read()
    dur = a.duration or get_duration(a.audio)
    if dur is None:
        sys.exit("ERROR: 需提供 --audio 或 --duration 以确定总时长")
    years = None
    inds = None
    if a.data:
        try:
            _dj = json.load(open(a.data, encoding='utf-8'))
            years = _dj['years']
            inds = _dj.get('industries') or []
        except Exception as e:
            sys.exit(f"ERROR: 读取 {a.data} 失败: {e}")
    global _NO_DENSIFY
    _NO_DENSIFY = a.no_densify
    pts = extract(text, dur, final_year=a.final_year, first_year=a.first_year,
                  intro=a.intro, tail_pad=a.tail, years=years, inds=inds)
    if not pts:
        sys.exit("ERROR: 未在解说稿中识别到任何 4 位年份，无法生成时间轴")
    # 按数据变化强度重排：口播锚点时刻不动，中间年份「剧变放慢、不动快进」
    if not a.no_densify and years is not None:
        try:
            _d = json.load(open(a.data, encoding='utf-8'))
            _before = len(pts)
            pts = densify(pts, years, _d.get('industries') or [])
            if len(pts) != _before:
                print("[timeline] 变化强度重排: %d -> %d 锚点" % (_before, len(pts)))
        except Exception as e:
            print("[timeline] 重排跳过：", repr(e))
    # 新格式：(t, idx)；旧格式：(t, year)。前端 build_race._idx_of() 双格式兼容。
    payload = []
    for t, y in pts:
        if isinstance(y, int) and 0 <= y < 10**8 and years is not None and y < len(years):
            payload.append({"t": round(t, 3), "idx": y, "year": int(str(years[y])[:4])})
        else:
            payload.append({"t": round(t, 3), "year": y})
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("duration=%.2fs  timeline points=%d" % (dur, len(payload)))
    for p in payload:
        if 'idx' in p:
            print("  t=%.2fs -> idx=%d (year=%d)" % (p['t'], p['idx'], p['year']))
        else:
            print("  t=%.2fs -> %d" % (p['t'], p['year']))


if __name__ == '__main__':
    main()
