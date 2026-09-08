# -*- coding: utf-8 -*-
"""整理交付编号：删掉被重做/残缺的旧片，把留下的重编号为连续号。

用法：
    python renumber.py --del 069,075 --map 070:069,071:070,076:074,077:075

- --del 要删除的编号（逗号分隔），通常是被重做版取代的旧片或无配音残缺版
- --map 重命名映射 `源:目标`（逗号分隔）。脚本按**源编号升序**处理，
  此时目标号均已腾空，不会互相覆盖。

每次跑完会校验 manifest 里的 file 是否都真实存在。
"""
import argparse
import json
import os

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'out', '增长与分化')


def _files(no):
    return [f for f in os.listdir(BASE)
            if f.startswith(no + '_') and (f.endswith('.mp4') or f.endswith('.md'))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--del', dest='del_nos', default='', help='要删除的编号，逗号分隔')
    ap.add_argument('--map', dest='map_str', default='',
                    help='重命名映射 源:目标，逗号分隔')
    a = ap.parse_args()

    dels = [x.strip() for x in a.del_nos.split(',') if x.strip()]
    pairs = []
    for item in a.map_str.split(','):
        item = item.strip()
        if not item:
            continue
        s, d = item.split(':')
        pairs.append((s.strip(), d.strip()))
    pairs.sort(key=lambda p: p[0])  # 升序，保证目标号已腾空

    removed = []
    for no in dels:
        for f in _files(no):
            os.remove(os.path.join(BASE, f))
            removed.append(f)
    print(f'删除旧版 {len(removed)} 个文件')
    for f in removed:
        print('   -', f)

    renamed = []
    for src, dst in pairs:
        for f in sorted(_files(src)):
            new = dst + f[len(src):]
            os.rename(os.path.join(BASE, f), os.path.join(BASE, new))
            renamed.append((f, new))
    print(f'重编号 {len(renamed)} 个文件')
    for x, y in renamed:
        print(f'   {x} -> {y}')

    # 同步 manifest
    mf = os.path.join(BASE, 'manifest.json')
    data = json.load(open(mf, encoding='utf-8'))
    m = dict(pairs)
    kept = []
    for it in data:
        if it.get('no') in dels:
            continue
        no = m.get(it.get('no'), it.get('no'))
        it['no'] = no
        it['file'] = f"{no}_{it.get('title', '')}.mp4"
        kept.append(it)
    json.dump(kept, open(mf, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'manifest：{len(data)} -> {len(kept)} 条')

    miss = [it['file'] for it in kept
            if not os.path.exists(os.path.join(BASE, it['file']))]
    print('缺失文件:', miss if miss else '无')


if __name__ == '__main__':
    main()
