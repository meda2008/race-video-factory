#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""按题材内容生成"相关但不抢数据"的背景提示词。

原来的背景是通用抽象渐变（"高级财经数据可视化背景，深色渐变…"），
每支片子长得都差不多，跟内容没关系。这里改成：先理解题材在讲什么，
再描述一幅**与之相关、但压得住数据**的画面。

三条硬约束（否则会盖住柱状图和数字）：
  1. 大面积暗部 + 低饱和，整体压暗
  2. 画面中下部（数据面板区）留白 / 景深虚化
  3. 无文字、无高对比亮斑、无具象人脸

输出写入缓存文件，同一题材只调一次 LLM。

用法:
  python bg_prompt.py --data <topic_x.json> --out <bg_prompt.txt> [--force] [--dry-run]
"""
import argparse, json, os, re, sys, time

FALLBACK = ('高级财经数据可视化背景，深色渐变，电影感，四角暗角，无文字，专业克制')

PROMPT = """你是数据可视化视频的背景美术。请为一个竖屏（9:16）竞速柱状图视频设计背景画面。

【这个视频在讲什么】
标题：{title}
副标题：{subtitle}
数值单位：{unit}
主题分类：{theme}

【要求】
1. 画面内容必须**和上面这个题材强相关**，让人一眼知道这条片子讲的是什么领域。
   例：讲军费 → 航母甲板/战机剪影；讲电影票房 → 影院座椅与银幕微光；
   讲碳排放 → 工厂烟囱与雾霾中的城市天际线；讲啤酒消费 → 麦芽与酒杯的暗调特写。
2. **必须压得住数据**（最关键）：
   - 整体暗调、低饱和，大面积暗部
   - 画面中下部（柱状图和数字所在区域）留白或景深虚化
   - 不要文字、不要高对比亮斑、不要人脸、不要杂乱细节
3. 电影感布光，四角压暗，竖构图。
4. 只输出**一段中文画面描述**（40~70 字），不要解释、不要英文、不要引号、不要分点。

直接输出描述："""


def _theme(title):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import run as _run
        return _run.infer_theme(title)
    except Exception:
        return 'finance'


def call_llm(prompt, timeout=120, tries=4):
    import requests
    p = os.path.join(os.path.expanduser('~'), '.workbuddy', 'models.json')
    data = json.load(open(p, encoding='utf-8-sig'))
    models = data if isinstance(data, list) else [data]
    base = key = model = None
    for m in models:
        if isinstance(m, dict) and m.get('apiKey') and m.get('url'):
            u = m['url'].rstrip('/')
            for suf in ('/chat/completions', '/responses', '/images/generations'):
                if u.endswith(suf):
                    u = u[: -len(suf)]
                    break
            base, key, model = u.rstrip('/'), m['apiKey'], (m.get('id') or 'gpt-5.6-sol')
            break
    if not base:
        raise SystemExit('ERROR: models.json 无可用模型')
    last = None
    for i in range(1, tries + 1):
        try:
            r = requests.post(base + '/chat/completions',
                              headers={'Content-Type': 'application/json',
                                       'Authorization': 'Bearer ' + key},
                              json={'model': model,
                                    'messages': [{'role': 'user', 'content': prompt}],
                                    'temperature': 0.8}, timeout=timeout)
            j = r.json()
            return ((j.get('choices') or [{}])[0].get('message') or {}).get('content', '').strip()
        except Exception as e:
            last = e
            print('[bgp] LLM 第 %d 次失败：%s' % (i, type(e).__name__))
            time.sleep(3 * i)
    raise last


def clean(t):
    t = (t or '').strip().strip('"').strip('「').strip('」').strip('。') + '。'
    t = re.sub(r'\s+', '', t)
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', required=True, help='缓存文件（背景提示词）')
    ap.add_argument('--force', action='store_true', help='忽略缓存重新生成')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--workspace', default=None,
                    help='兼容 run.py 统一签名（py() 总会带 --workspace），本脚本不使用')
    a = ap.parse_args()

    # 缓存命中且未强制 -> 直接复用
    if os.path.exists(a.out) and os.path.getsize(a.out) > 10 and not a.force:
        print('[bgp] 复用缓存 ->', a.out)
        return 0

    d = json.load(open(a.data, encoding='utf-8'))
    meta = d.get('meta') or {}
    title = meta.get('title') or ''
    subtitle = meta.get('subtitle') or ''
    unit = meta.get('unit') or ''
    theme = _theme(title)

    if a.dry_run:
        print('[bgp] dry-run | 标题=%s | 主题=%s' % (title, theme))
        return 0

    prompt = PROMPT.format(title=title or '数据排名变化', subtitle=subtitle,
                           unit=unit, theme=theme)
    try:
        desc = clean(call_llm(prompt))
    except Exception as e:
        print('[bgp] LLM 失败，回退通用背景：', repr(e))
        desc = ''
    # 无论 LLM 成败，都补上"压得住数据"的刚性后缀
    suffix = '整体暗调低饱和，中下部大面积留白适合叠加数据，无文字无高对比亮斑，电影感布光，四角压暗，竖构图'
    final = (desc + suffix) if desc and len(desc) >= 12 else FALLBACK

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, 'w', encoding='utf-8').write(final + '\n')
    print('[bgp] %s -> %s' % (title[:20], final[:60]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
