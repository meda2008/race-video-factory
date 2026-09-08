# -*- coding: utf-8 -*-
"""扫描所有题材配置里会显示在画面上的英文字段。

关注字段：title / subtitle / legend / unit / source / highlight。
输出：每个英文词出现次数 + 出现在哪些题材，供人工决定中文化方案。
"""
import json
import glob
import os
import re
import sys
from collections import defaultdict

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(WS)

# 画面主体字段（不含 source/src，来源说明保留技术英文以便溯源）
FIELDS = ('title', 'subtitle', 'legend', 'unit', 'highlight', 'valueLabel')
WORD = re.compile(r'[A-Za-z][A-Za-z0-9&+.\-]{1,30}')

# 不算「需要中文化的英文」：季度/月份标签、纯数字单位、URL
SKIP = {
    'Q1', 'Q2', 'Q3', 'Q4', 'http', 'https', 'www', 'com', 'org', 'net', 'cn', 'html',
    'json', 'csv', 'api', 'mp4', 'png', 'jpg', 'ID',
}


def walk(o, path, out):
    if isinstance(o, dict):
        for k, v in o.items():
            walk(v, path + [str(k)], out)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, path + ['%d' % i], out)
    elif isinstance(o, str):
        for m in WORD.findall(o):
            if m in SKIP:
                continue
            out.append((m, '.'.join(path), o[:80]))


def main():
    files = sorted(glob.glob('topics_registry_*.json'))
    hit = defaultdict(list)   # word -> [(file, path, snippet)]
    for f in files:
        try:
            data = json.load(open(f, encoding='utf-8'))
        except Exception as e:
            print('跳过 %s: %s' % (f, e))
            continue
        out = []
        if isinstance(data, dict):
            # 两种结构：{slug: cfg} 或 {"topics": [cfg...]}
            if 'topics' in data and isinstance(data['topics'], list):
                for i, t in enumerate(data['topics']):
                    walk(t, ['topics[%d]' % i], out)
            else:
                for k, v in data.items():
                    if isinstance(v, dict):
                        walk(v, [k], out)
        for w, p, sn in out:
            # 只看画面字段
            if not any(seg in ('title', 'subtitle', 'legend', 'unit', 'highlight',
                               'valueLabel') for seg in p.split('.')):
                continue
            hit[w].append((f, p, sn))

    print('=== 画面字段中的英文词（按出现题材数排序）===')
    rows = sorted(hit.items(), key=lambda kv: (-len(set(x[0] + x[1] for x in kv[1])), kv[0]))
    for w, lst in rows:
        keys = sorted(set('%s :: %s' % (a, b) for a, b, _ in lst))
        print('\n【%s】 出现 %d 次' % (w, len(lst)))
        for k in keys[:6]:
            print('    %s' % k)
        if len(keys) > 6:
            print('    ... 还有 %d 处' % (len(keys) - 6))
    print('\n共 %d 个不同的英文词' % len(rows))


if __name__ == '__main__':
    main()
