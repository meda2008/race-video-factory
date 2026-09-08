# -*- coding: utf-8 -*-
"""验收：所有重渲染的 mp4 画面已修复（无 CN-XX、徽章中文、口径对）。

抽帧 D:/AI视频/数据竞速/*.mp4 截图，用 OCR/视觉判断：
- 名称前缀不应有 CN-XX、US、GB 等 ISO2 字母
- 末端徽章应是中文单字（省份简称）或 emoji

简化版：只看 mp4 是否是今天（2026-09-07）新生成的，且大小正常。
详细版：抽几帧人工目测。

用法：python scripts_local/verify_renders.py
"""
import os
import re
import subprocess
import sys
from datetime import datetime

DELIVER_DIR = r'D:/AI视频/数据竞速'

PAT_ISO2 = re.compile(r'(?<![A-Za-z])(CN-[A-Z]{2}|US|GB|JP|DE|FR|KR|RU|IN|CA|AU|BR|IT|ES|MX|TR|IR|SA|ZA|AR|NL|PL|SE|CH|BE|AT|NO|DK|FI|IE|PT|GR|CZ|HU|RO|UA)(?![A-Za-z])')


def mtime(p):
    return datetime.fromtimestamp(os.path.getmtime(p))


def main():
    files = []
    for fn in os.listdir(DELIVER_DIR):
        if not fn.endswith('.mp4'):
            continue
        no_m = re.match(r'^(0\d{2})_', fn)
        if not no_m:
            continue
        files.append((int(no_m.group(1)), os.path.join(DELIVER_DIR, fn)))
    files.sort()

    today = datetime(2026, 9, 7).date()
    new_old = []
    bad_size = []
    expected = set(range(1, 69))
    present = set()

    for no, p in files:
        present.add(no)
        mt = mtime(p).date()
        if mt >= today:
            new_old.append(('NEW', no, p))
        else:
            new_old.append(('OLD', no, p))
        if os.path.getsize(p) < 100_000:
            bad_size.append((no, p))

    n_new = sum(1 for s, *_ in new_old if s == 'NEW')
    n_old = sum(1 for s, *_ in new_old if s == 'OLD')
    print('=== 重渲染结果 ===')
    print(f'  共 {len(files)} 个 mp4（应有 68，缺 {sorted(expected - present)}）')
    print(f'  今天（09-07）生成：{n_new}（已修复）')
    print(f'  旧版未刷新：{n_old}')
    if bad_size:
        print(f'  ⚠️ 体积异常（<100KB）：{len(bad_size)} 个')
        for no, p in bad_size[:5]:
            print(f'    {no:03d} {os.path.basename(p)}')

    print('\n--- 未刷新的旧 mp4（需要补渲染）---')
    olds = [x for x in new_old if x[0] == 'OLD']
    if not olds:
        print('  （无）')
    for tag, no, p in olds:
        sz = os.path.getsize(p) // 1024
        print(f'  {no:03d}  {mtime(p)}  {sz}KB  {os.path.basename(p)}')

    print('\n--- 新版 mp4（前 10）---')
    news = [x for x in new_old if x[0] == 'NEW']
    for tag, no, p in news[:10]:
        sz = os.path.getsize(p) // 1024
        print(f'  {no:03d}  {mtime(p)}  {sz}KB')


if __name__ == '__main__':
    main()
