# -*- coding: utf-8 -*-
"""只补交付：把 out/topic_<slug>.mp4 按原编号送到 D:/AI视频/数据竞速。

用于渲染成功但 deliver 被守卫杀掉的补救，避免整支重渲染。
用法: python deliver_only.py [--dry-run]
"""
import glob, json, os, subprocess, sys

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = 'C:/Users/medam/.workbuddy/binaries/python/envs/default/Scripts/python.exe'
DELIVER = 'C:/Users/medam/.workbuddy/skills/finance-ranking-video/scripts/deliver.py'
OUTDIR = 'D:/AI视频/数据竞速'
S2N = os.path.join(WS, 'data', 'slug2no.json')

no_map = json.load(open(S2N, encoding='utf-8')) if os.path.exists(S2N) else {}
dry = '--dry-run' in sys.argv

ok, miss, fail = [], [], []
for src in sorted(glob.glob(os.path.join(WS, 'out', 'topic_*.mp4'))):
    slug = os.path.basename(src)[6:-4]
    if slug.endswith('.delivered'):
        continue
    meta = os.path.join(WS, 'data', 'topic_%s_post_meta.json' % slug)
    if not os.path.exists(meta):
        miss.append((slug, '无 meta'))
        continue
    try:
        title = json.load(open(os.path.join(WS, 'data', 'topic_%s.json' % slug),
                               encoding='utf-8'))['meta']['title']
    except Exception:
        try:
            title = json.load(open(meta, encoding='utf-8')).get('titles', [slug])[0]
        except Exception:
            title = slug
    num = no_map.get(slug)
    cmd = [PY, DELIVER, '--src', 'out/topic_%s.mp4' % slug, '--title', title,
           '--meta', 'data/topic_%s_post_meta.json' % slug,
           '--kind', 'topic_%s' % slug, '--outdir', OUTDIR]
    if num:
        cmd += ['--no', str(num)]
    print('===', slug, '-> no', num, '|', title)
    if dry:
        continue
    p = subprocess.run(cmd, cwd=WS, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if p.returncode == 0:
        ok.append(slug)
        print('   OK')
    else:
        fail.append(slug)
        print('   FAIL:', (p.stdout or '')[-300:], (p.stderr or '')[-300:])

print('\n成功 %d / 失败 %d / 跳过 %d' % (len(ok), len(fail), len(miss)))
if fail:
    print('失败:', ', '.join(fail))
if miss:
    print('跳过:', miss)
