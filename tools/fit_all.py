# -*- coding: utf-8 -*-
"""批量跑口播稿长度定制（fit_narration），不渲染。

先单独跑一遍再渲染，好处：LLM 调用集中在一段，渲染时稿子已就绪、不会再等网络。
用法: python fit_all.py [--only a,b] [--limit N] [--force]
"""
import glob, json, os, subprocess, sys, time

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = 'C:/Users/medam/.workbuddy/binaries/python/envs/default/Scripts/python.exe'
FIT = 'C:/Users/medam/.workbuddy/skills/finance-ranking-video/scripts/fit_narration.py'

only, limit, force = set(), None, False
argv = sys.argv[1:]
for i, a in enumerate(argv):
    if a == '--only' and i + 1 < len(argv):
        only = set(x.strip() for x in argv[i + 1].split(',') if x.strip())
    elif a == '--limit' and i + 1 < len(argv):
        limit = int(argv[i + 1])
    elif a == '--force':
        force = True

slugs = []
for p in sorted(glob.glob(os.path.join(WS, 'data', 'topic_*.json'))):
    b = os.path.basename(p)[6:-5]
    if b and not b.endswith('_post_meta'):
        slugs.append((b, p))
slugs = [(s, p) for s, p in slugs
         if os.path.exists(os.path.join(WS, 'data', 'topic_%s_narration.txt' % s))]
if only:
    slugs = [(s, p) for s, p in slugs if s in only]
slugs.sort()
if limit:
    slugs = slugs[:limit]

print('待处理口播稿：%d 篇' % len(slugs))
ok, skip, fail = [], [], []
t0 = time.time()
for i, (slug, dpath) in enumerate(slugs, 1):
    src = os.path.join(WS, 'data', 'topic_%s_narration.txt' % slug)
    cmd = [PY, FIT, '--data', dpath, '--src', src]
    r = subprocess.run(cmd, cwd=WS, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    out = ((r.stdout or '') + (r.stderr or '')).strip().splitlines()
    line = out[-1] if out else ''
    if '已扩充' in line or '已精简' in line:
        ok.append(slug)
        print('[%d/%d] %-26s %s' % (i, len(slugs), slug, line.strip()))
    elif '长度已合适' in line or '保留原稿' in line:
        skip.append(slug)
        print('[%d/%d] %-26s %s' % (i, len(slugs), slug,
                                    line.strip() or '保留原稿'))
    else:
        fail.append(slug)
        print('[%d/%d] %-26s FAIL %s' % (i, len(slugs), slug, line.strip()[:120]))

print('\n===== 改写 %d / 保持 %d / 失败 %d | 耗时 %.1f 分钟' % (
    len(ok), len(skip), len(fail), (time.time() - t0) / 60))
if fail:
    print('失败：', ', '.join(fail))
