# -*- coding: utf-8 -*-
"""自检：所有题材的实体徽章文字是否还有拉丁字母。

画面徽章一律用中文单字（省份简称/国家首字）或 emoji；
只有「品牌名本身就是拉丁字母」的（AMD / vivo / ASML…）允许保留，
那属于实体名本身，不属于流程 bug。

用法：python scripts_local/check_badge_latin.py
"""
import csv
import glob
import importlib.util
import os
import re
import sys

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(WS)

SKILL = os.path.join(os.path.dirname(WS), '..', '..', '.workbuddy', 'skills',
                     'finance-ranking-video', 'scripts', 'emoji_lib.py')
SKILL = os.path.abspath(SKILL)
spec = importlib.util.spec_from_file_location('emoji_lib', SKILL)
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)

LATIN = re.compile(r'[A-Za-z]')
EMOJI = re.compile(r'[\U0001F000-\U0001FAFF\u2600-\u27BF]')


def main():
    files = sorted(glob.glob('data/topics_csv/*.csv'))
    if not files:
        print('没找到 CSV')
        return 1
    latin_rows = []
    total = 0
    for f in files:
        if os.path.basename(f).startswith('_bak'):
            continue
        try:
            rows = list(csv.reader(open(f, encoding='utf-8-sig')))
        except Exception:
            continue
        for r in rows[1:]:
            if not r:
                continue
            name = r[0].split('|')[0].strip()
            if not name:
                continue
            total += 1
            icon = E.icon_for(name)
            if LATIN.search(str(icon)):
                latin_rows.append((os.path.basename(f), name, icon))

    print('共检查 %d 个实体名' % total)
    if not latin_rows:
        print('✅ 徽章文字无拉丁字母')
        return 0
    print('\n⚠️ 仍有 %d 个实体徽章含拉丁字母（按文件聚合）：' % len(latin_rows))
    from collections import defaultdict
    g = defaultdict(list)
    for f, n, i in latin_rows:
        g[f].append('%s→%s' % (n, i))
    for f in sorted(g):
        print('\n  %s（%d）' % (f, len(g[f])))
        print('    ' + '，'.join(g[f][:14]))
        if len(g[f]) > 14:
            print('    ... 还有 %d 个' % (len(g[f]) - 14))
    return 0


if __name__ == '__main__':
    sys.exit(main())
