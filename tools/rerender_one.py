# -*- coding: utf-8 -*-
"""单支重渲染：move 方式清理旧产物（不触发 safe-delete），覆盖回原编号、清 manifest 重复。
用法：python rerender_one.py <key> <registry.json>"""
import os, re, json, shutil, subprocess, sys, time

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(WS, 'out', '增长与分化')
MAN = os.path.join(OUT, 'manifest.json')
RUN = 'C:/Users/medam/.workbuddy/skills/finance-ranking-video/scripts/run.py'
PY = 'C:/Users/medam/.workbuddy/binaries/python/envs/default/Scripts/python.exe'
DATA_TRASH = os.path.join(WS, 'data', '_trash_rerender')
OUT_TRASH = os.path.join(OUT, '_trash_rerender')

def _move(p):
    if not os.path.exists(p):
        return
    tdir = DATA_TRASH if p.startswith(os.path.join(WS, 'data')) else OUT_TRASH
    os.makedirs(tdir, exist_ok=True)
    dst = os.path.join(tdir, os.path.basename(p))
    if os.path.exists(dst):
        dst = os.path.join(tdir, '_%d_%s' % (int(time.time() * 1000), os.path.basename(p)))
    shutil.move(p, dst)

def stale_files(key):
    base = os.path.join(WS, 'data', 'topic_%s' % key)
    for suf in ['_narration.txt', '_wechat_narration.txt', '_post_meta.json',
                '_wechat_post_meta.json', '_post_meta.txt', '_wechat_post_meta.txt',
                '_timeline.json']:
        _move(base + suf)

def run_one(key, reg):
    regp = os.path.join(WS, reg)
    cmd = [PY, RUN, 'topic_config', '--key', key, '--registry', regp,
           '--workspace', WS, '--no-ai']
    out = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=900)
    txt = out.stdout + out.stderr
    m = re.search(r'编号=(\d+)', txt)
    if not m:
        raise RuntimeError('未从输出解析到编号；stdout尾:\n' + txt[-800:])
    return m.group(1)

def replace(key, new_no):
    kind = 'topic_%s' % key
    man = json.load(open(MAN, encoding='utf-8'))
    entries = [e for e in man if e.get('kind') == kind]
    if len(entries) < 2:
        print('  [warn] %s 未找到重复条目，跳过替换' % key); return
    new_entry = next(e for e in entries if e['file'].startswith(new_no + '_'))
    old_entry = next(e for e in entries if not e['file'].startswith(new_no + '_'))
    new_path = os.path.join(OUT, new_entry['file'])
    old_path = os.path.join(OUT, old_entry['file'])
    shutil.copyfile(new_path, old_path)
    new_md = os.path.join(OUT, new_entry['file'].replace('.mp4', '_发布文案.md'))
    old_md = os.path.join(OUT, old_entry['file'].replace('.mp4', '_发布文案.md'))
    if os.path.exists(new_md):
        shutil.copyfile(new_md, old_md); _move(new_md)
    _move(new_path)
    man2 = [e for e in man if e is not new_entry]
    for e in man2:
        if e.get('kind') == kind and e['file'] == old_entry['file']:
            e['created_at'] = new_entry.get('created_at', e['created_at'])
    json.dump(man2, open(MAN, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('  %s 已覆盖 %s，manifest 剩余 %d 条' % (key, old_path, len(man2)))

if __name__ == '__main__':
    key, reg = sys.argv[1], sys.argv[2]
    print('===== 重渲染 %s (%s) =====' % (key, reg))
    stale_files(key)
    ok = False
    for attempt in (1, 2):
        try:
            new_no = run_one(key, reg)
            print('  生成编号 %s' % new_no)
            replace(key, new_no)
            ok = True
            break
        except Exception as e:
            print('  [attempt %d 失败] %s' % (attempt, repr(e)[:300]))
    if not ok:
        print('  !!! %s 重渲染失败，保留原片' % key)
    print('DONE')
