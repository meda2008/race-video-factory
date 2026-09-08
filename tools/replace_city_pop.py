# -*- coding: utf-8 -*-
"""把 city_pop 新渲染的 074_ 覆盖回原 001_ 并清理 manifest 重复。"""
import os, json, shutil
WS = 'C:/Users/medam/WorkBuddy/视频测试/batch2_ws'
OUT = os.path.join(WS, 'out', '增长与分化')
MAN = os.path.join(OUT, 'manifest.json')
key = 'city_pop'
kind = 'topic_%s' % key
new_no = '074'
man = json.load(open(MAN, encoding='utf-8'))
entries = [e for e in man if e.get('kind') == kind]
assert len(entries) >= 2, '条目不足: %r' % [e['file'] for e in entries]
new_entry = next(e for e in entries if e['file'].startswith(new_no + '_'))
old_entry = next(e for e in entries if not e['file'].startswith(new_no + '_'))
new_path = os.path.join(OUT, new_entry['file'])
old_path = os.path.join(OUT, old_entry['file'])
shutil.copyfile(new_path, old_path)
new_md = os.path.join(OUT, new_entry['file'].replace('.mp4', '_发布文案.md'))
old_md = os.path.join(OUT, old_entry['file'].replace('.mp4', '_发布文案.md'))
if os.path.exists(new_md):
    shutil.copyfile(new_md, old_md); os.remove(new_md)
os.remove(new_path)
man2 = [e for e in man if e is not new_entry]
for e in man2:
    if e.get('kind') == kind and e['file'] == old_entry['file']:
        e['created_at'] = new_entry.get('created_at', e['created_at'])
json.dump(man2, open(MAN, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('city_pop 已覆盖 %s，manifest 剩余 %d 条' % (old_path, len(man2)))
