# -*- coding: utf-8 -*-
"""按交付目录里的真实文件回填 manifest 的 file / title 字段。

背景：cn_vs_world 分支（033–042）归档时，实际文件名带题材前缀
（如 `033_光伏——中国用13年从跟跑变领跑_一张图看懂中外产业逆袭🏁.mp4`），
而 manifest 里记的却是清洗掉前缀后的短标题，导致 10 条记录指向不存在的文件，
归档检索直接失效。这里以磁盘上的真实文件为准，按编号前缀回填。
"""
import json
import os

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'out', '增长与分化')
MF = os.path.join(BASE, 'manifest.json')


def main():
    real = {}
    for f in os.listdir(BASE):
        if f.endswith('.mp4') and f[:3].isdigit() and f[3] == '_':
            real.setdefault(f[:3], []).append(f)

    data = json.load(open(MF, encoding='utf-8'))
    fixed = 0
    for it in data:
        no = it.get('no')
        cands = real.get(no, [])
        if not cands:
            continue
        # 同号多文件时取唯一一个；若当前 file 已在磁盘上则不动
        cur = it.get('file')
        if cur in cands:
            continue
        target = cands[0]
        it['file'] = target
        it['title'] = target[4:-4]  # 去掉 "NNN_" 与 ".mp4"
        fixed += 1

    json.dump(data, open(MF, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'回填 {fixed} 条；manifest 共 {len(data)} 条')

    miss = [it['file'] for it in data
            if not os.path.exists(os.path.join(BASE, it['file']))]
    print('仍缺失:', miss if miss else '无')
    # 反向检查：磁盘上有但 manifest 没记的
    known = {it['file'] for it in data}
    orphan = [f for fs in real.values() for f in fs if f not in known]
    print('未登记:', orphan if orphan else '无')


if __name__ == '__main__':
    main()
