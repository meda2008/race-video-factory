#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""按「磁盘上的真实文件」重建项目清单 <outdir>/manifest.json。

背景（2026-09-16 实测）：`deliver.py` 以前是盲目 `man.append`，重渲染一次多一条，
项目清单膨胀到 382 条，其中 97 条指向已不存在的文件、编号 074 一个号挂了 45 条。
根清单 `D:\\AI视频\\manifest.json` 有去重所以是干净的，但项目内那一份早就烂了。

修法是两条一起：
  1. `deliver.py` 写入时按 (编号, 文件名) 去重（已改）
  2. 存量用本脚本按磁盘真实文件重建一次

用法：
  python tools/rebuild_manifest.py --dir D:\\AI视频\\数据竞速
  python tools/rebuild_manifest.py --dir D:\\AI视频\\数据竞速 --root D:\\AI视频\\manifest.json
  python tools/rebuild_manifest.py --dir ... --dry-run     # 只看不写
"""
import argparse, json, os, glob, datetime

DEFAULT_ROOT = r'D:\AI视频\manifest.json'


def load_root(root, project):
    """从根清单取 (file) -> entry，用于回填编号/标题/题材/时间。"""
    out = {}
    if not (root and os.path.isfile(root)):
        return out
    try:
        d = json.load(open(root, encoding='utf-8'))
    except Exception:
        return out
    for e in d.get('videos', []):
        if e.get('project') == project and e.get('file'):
            out[e['file']] = e
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=r'D:\AI视频\数据竞速')
    ap.add_argument('--root', default=DEFAULT_ROOT)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    d = os.path.abspath(a.dir)
    project = os.path.basename(d.rstrip('\\/'))
    root = load_root(a.root, project)
    files = sorted(glob.glob(os.path.join(d, '*.mp4')))
    if not files:
        print('没有 mp4：', d)
        return 1

    rows = []
    for f in files:
        name = os.path.basename(f)
        no = name[:3] if name[:3].isdigit() else ''
        title = os.path.splitext(name[4:] if no else name)[0]
        e = root.get(name) or {}
        rows.append({
            'no': e.get('no') or no,
            'title': e.get('title') or title,
            'file': name,
            'kind': e.get('kind') or '',
            'created_at': e.get('created_at')
                          or datetime.datetime.fromtimestamp(
                              os.path.getmtime(f)).strftime('%Y-%m-%d %H:%M'),
            'original': e.get('original') or '',
        })
    rows.sort(key=lambda r: (str(r['no']), r['file']))

    man_path = os.path.join(d, 'manifest.json')
    old = []
    if os.path.isfile(man_path):
        try:
            old = json.load(open(man_path, encoding='utf-8'))
        except Exception:
            old = []
    print('项目：%s' % project)
    print('磁盘 mp4：%d 支｜原清单 %d 条 → 重建后 %d 条'
          % (len(files), len(old), len(rows)))
    if a.dry_run:
        for r in rows[:10]:
            print('  ', r['no'], r['file'])
        return 0
    bak = man_path + '.bak_' + datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    try:
        with open(bak, 'w', encoding='utf-8') as f:
            json.dump(old, f, ensure_ascii=False, indent=2)
        print('原清单已备份 ->', bak)
    except OSError as e:
        print('备份失败（已中止）：', e)
        return 1
    with open(man_path, 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print('已重建 ->', man_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
