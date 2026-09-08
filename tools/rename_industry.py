# -*- coding: utf-8 -*-
"""把 industry_salary 成品文件名 1995–2024 → 1995–2025（仅改名，move 不触发 safe-delete）。
同步改名 发布文案.md 并更新 manifest 的 file 字段。"""
import os, json, shutil

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(WS, 'out', '增长与分化')
MAN = os.path.join(OUT, 'manifest.json')
OLD_MP4 = '014_各行业平均薪酬变迁（1995–2024）.mp4'
NEW_MP4 = '014_各行业平均薪酬变迁（1995–2025）.mp4'
OLD_MD = '014_各行业平均薪酬变迁（1995–2024）_发布文案.md'
NEW_MD = '014_各行业平均薪酬变迁（1995–2025）_发布文案.md'

mp4_src = os.path.join(OUT, OLD_MP4)
mp4_dst = os.path.join(OUT, NEW_MP4)
md_src = os.path.join(OUT, OLD_MD)
md_dst = os.path.join(OUT, NEW_MD)

if os.path.exists(mp4_src):
    os.rename(mp4_src, mp4_dst)
    print('mp4 renamed')
else:
    print('mp4 not found:', OLD_MP4)
if os.path.exists(md_src):
    os.rename(md_src, md_dst)
    print('md renamed')

man = json.load(open(MAN, encoding='utf-8'))
for e in man:
    if e.get('kind') == 'topic_industry_salary' and e.get('file') == OLD_MP4:
        e['file'] = NEW_MP4
        print('manifest updated')
json.dump(man, open(MAN, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('DONE')
