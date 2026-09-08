#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""口播稿长度定制：按"数据内容量"反推目标时长 -> 目标字数 -> 改写口播稿。

为什么需要：数据只有 11 个点的题材和 260 个点的题材，稿子长度本来就该不同。
以前是"写多长算多长"，短片 13 秒、长片 151 秒；长片再靠加速压回来，等于
用 1.3 倍速念一篇本该删减的稿子。

流程：
  1) target_duration(years)  -> 目标时长（秒）
  2) 目标字数 = 时长 × CHARS_PER_SEC（中文播报实测 ≈4.8 字/秒）
  3) 现有稿子偏离目标 ±TOL 以外时，交给 LLM 按真实数据摘要改写
     （只能引用摘要里的数字，禁止编造）

用法:
  python fit_narration.py --data <topic_x.json> --src <narration.txt> [--out ...] [--dry-run]
"""
import argparse, json, os, re, sys, time

CHARS_PER_SEC = 4.8        # 实测：163字→33.5s、758字→151.5s ≈ 4.8~5.0 字/秒
TOL = 0.18                 # 偏离目标 ±18% 以内不动稿，避免无谓改写
MIN_DUR, MAX_DUR = 32.0, 105.0
MIN_CHARS, MAX_CHARS = 140, 520
# 时长 = 基础值 + 年度跨度 × 每年秒数。年度跨度越长讲得越久（用户要求），
# 但仍受 MAX_DUR 封顶，保证单支不超过 2 分钟。
BASE_SEC = 18.0
SEC_PER_YEAR = 1.25


def year_span(years):
    """首末年跨度（年）。标签可能是 '2015' / '1950Q4' / '2004-12'，统一取前 4 位年份。"""
    def y(s):
        m = re.search(r'(19|20)\d{2}', str(s))
        return int(m.group(0)) if m else None
    a, b = y(years[0]), y(years[-1])
    if a is None or b is None:
        return len(years) / 4.0          # 解析失败：按每季度≈1/4年粗略折算
    return max(1.0, float(b - a))


def val_at(it, y, years):
    v = it.get('values')
    if isinstance(v, dict):
        return v.get(str(y))
    if isinstance(v, (list, tuple)):
        i = list(years).index(y) if y in years else -1
        return v[i] if 0 <= i < len(v) else None
    return None


def target_duration(years, inds=None):
    """目标时长：按**年度跨度**走——覆盖的年份越长，讲得越久（用户要求）。

    公式：BASE_SEC + 年度跨度 × SEC_PER_YEAR，封顶 MAX_DUR（保证 ≤2 分钟）。
    例：10 年 → 30.5s；33 年 → 59s；70 年 → 105s；124 年 → 105s（封顶）。
    """
    span = year_span(years)
    return max(MIN_DUR, min(MAX_DUR, BASE_SEC + span * SEC_PER_YEAR))


def digest(years, inds, meta, topk=5, key_years=6):
    """真实数据摘要——LLM 只能引用这里的数字，杜绝编造。"""
    L = []
    unit = (meta or {}).get('unit') or ''
    dec = int((meta or {}).get('decimals') or 0)

    def fmt(v):
        if v is None:
            return '—'
        try:
            return ('%.*f' % (dec, v)).rstrip('0').rstrip('.')
        except Exception:
            return str(v)

    def top_at(y):
        rows = []
        for it in inds or []:
            v = val_at(it, y, years)
            if isinstance(v, (int, float)):
                rows.append((it.get('name'), v))
        rows.sort(key=lambda r: -r[1])
        return rows[:topk]

    L.append('年份跨度：%s → %s，共 %d 个时间点' % (years[0], years[-1], len(years)))
    L.append('单位：%s' % (unit or '（无）'))

    for tag, y in (('首年', years[0]), ('末年', years[-1])):
        rows = top_at(y)
        if rows:
            L.append('%s %s 前%d名：%s' % (tag, y, len(rows),
                     '、'.join('%s %s' % (n, fmt(v)) for n, v in rows)))

    # 变化最剧烈的几个年份（名次变动总量最大）
    if len(years) > 2:
        ranks = {}
        for y in years:
            rows = top_at(y)
            ranks[y] = {n: i for i, (n, _) in enumerate(rows)}
        churn = []
        for i in range(1, len(years)):
            y0, y1 = years[i - 1], years[i]
            s = 0
            for n, r in ranks.get(y1, {}).items():
                if n in ranks.get(y0, {}):
                    s += abs(r - ranks[y0][n])
            churn.append((s, y1))
        churn.sort(reverse=True)
        picks = [y for s, y in churn[:key_years] if s > 0]
        for y in picks:
            rows = top_at(y)
            if rows:
                L.append('变动年 %s 前%d名：%s' % (y, min(3, len(rows)),
                         '、'.join('%s %s' % (n, fmt(v)) for n, v in rows[:3])))
    return '\n'.join(L)


PROMPT = """你是财经短视频的口播稿编辑。请基于【真实数据】改写口播稿，严格控制在目标字数附近。

【必须做到】
1. 每个数字必须能在【真实数据】里找到；**禁止**推算、插值、编造。
2. **数字取整到好念的位数**：101.72亿 念成"约102亿"，38800 念成"约3.9万"。口播不是报表。
3. 有对比/反差/反转：谁反超了谁、谁掉队了、差距是拉大还是缩小。要说**具体名字和数字**。
4. 按时间顺序推进，中间挑 2~4 个关键年份讲变化，不要只讲首尾两年。
5. 结尾用"数据来源：xxx"收尾（沿用原稿的来源说法）。

【严禁（出现即不合格）】
- 空泛感叹/套话：十分醒目、清清楚楚、显而易见、引人注目、不容忽视、值得一提、
  不是…而是…、可以看到、总的来说、综上所述、反差很直观、明显反超起点
- 小标题、序号、括号注释、Markdown 标记、英文单词
- 英文缩写：GDP→国内生产总值、AI→人工智能、ETF→指数基金、CPI→物价指数、Top10→前十

【目标】{target} 字（±{tol} 字）。当前 {cur} 字，需要{action}。

【真实数据】
{digest}

【当前口播稿】
{narr}

直接输出改写后的完整口播稿正文，不要任何前言和说明："""


def _cfg():
    cfg_path = os.path.join(os.path.expanduser('~'), '.workbuddy', 'models.json')
    data = json.load(open(cfg_path, encoding='utf-8-sig'))
    models = data if isinstance(data, list) else [data]
    for m in models:
        if isinstance(m, dict) and m.get('apiKey') and m.get('url'):
            url = m['url'].rstrip('/')
            for suf in ('/chat/completions', '/responses', '/images/generations'):
                if url.endswith(suf):
                    url = url[: -len(suf)]
                    break
            return url.rstrip('/'), m['apiKey'], (m.get('id') or 'gpt-5.6-sol')
    raise SystemExit('ERROR: models.json 无可用模型')


def call_llm(prompt, timeout=180, tries=4):
    """调 LLM。公司代理会偶发 SSL EOF，必须重试（实测 2~3 次内必通）。"""
    import requests
    base, key, model = _cfg()
    last = None
    for i in range(1, tries + 1):
        try:
            r = requests.post(base + '/chat/completions',
                              headers={'Content-Type': 'application/json',
                                       'Authorization': 'Bearer ' + key},
                              json={'model': model,
                                    'messages': [{'role': 'user', 'content': prompt}],
                                    'temperature': 0.7},
                              timeout=timeout)
            j = r.json()
            return ((j.get('choices') or [{}])[0].get('message') or {}).get('content', '').strip()
        except Exception as e:
            last = e
            print('[fit] LLM 第 %d 次失败：%s' % (i, type(e).__name__))
            time.sleep(3 * i)
    raise last


def clean(txt):
    txt = txt.strip()
    txt = re.sub(r'^```[a-zA-Z]*\n?', '', txt)
    txt = re.sub(r'\n?```$', '', txt)
    return txt.strip().strip('"').strip('「').strip('」')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True, help='归一化题材 JSON')
    ap.add_argument('--src', required=True, help='原口播稿')
    ap.add_argument('--out', default=None, help='输出（默认覆盖 --src）')
    ap.add_argument('--max-dur', type=float, default=MAX_DUR)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--workspace', default=None,
                    help='兼容 run.py 的统一调用签名（py() 总会带 --workspace），本脚本不使用')
    a = ap.parse_args()

    d = json.load(open(a.data, encoding='utf-8'))
    years, inds = d.get('years') or [], d.get('industries') or []
    meta = d.get('meta') or {}
    narr = open(a.src, encoding='utf-8').read().strip()

    dur = min(target_duration(years, inds), a.max_dur)
    target = int(max(MIN_CHARS, min(MAX_CHARS, round(dur * CHARS_PER_SEC))))
    cur = len(re.sub(r'\s', '', narr))
    lo, hi = int(target * (1 - TOL)), int(target * (1 + TOL))

    print('[fit] 年度跨度 %.0f 年 -> 目标 %.0fs -> 目标 %d 字（允许 %d~%d）｜当前 %d 字'
          % (year_span(years), dur, target, lo, hi, cur))
    if lo <= cur <= hi:
        print('[fit] 长度已合适，保留原稿')
        return 0

    action = '扩充' if cur < lo else '精简'
    prompt = PROMPT.format(target=target, tol=max(20, int(target * 0.08)), cur=cur,
                           action=action, digest=digest(years, inds, meta), narr=narr)
    if a.dry_run:
        print('[fit] dry-run，prompt 已生成，未调用 LLM')
        return 0
    try:
        out = clean(call_llm(prompt))
    except Exception as e:
        print('[fit] LLM 失败，保留原稿：', repr(e))
        return 1
    n2 = len(re.sub(r'\s', '', out))
    if n2 < target * 0.6 or n2 > target * 1.6 or len(out) < 40:
        print('[fit] 改写结果异常（%d 字），保留原稿' % n2)
        return 1
    dst = a.out or a.src
    # 改写前备份原稿（只备一次，避免二次运行把改写稿当成原稿）
    bak = a.src + '.orig'
    if not os.path.exists(bak):
        try:
            open(bak, 'w', encoding='utf-8').write(narr + '\n')
            print('[fit] 原稿已备份 ->', bak)
        except OSError:
            pass
    open(dst, 'w', encoding='utf-8').write(out + '\n')
    print('[fit] 已%s：%d 字 -> %d 字 -> %s' % (action, cur, n2, dst))
    return 0


if __name__ == '__main__':
    sys.exit(main())
