# -*- coding: utf-8 -*-
"""把题材配置里「会显示在画面上」的英文改成中文。

只处理 title / subtitle / legend / unit / highlight —— **不碰 source / src**：
来源说明里的 akshare 函数名、WDI 指标码（NY.GDP.MKTP.CD）、OWID slug
是溯源凭据，改成中文会破坏可查性。

用法：
    python scripts_local/apply_ui_cn.py --dry-run
    python scripts_local/apply_ui_cn.py
"""
import json
import glob
import os
import re
import sys
import shutil
from datetime import datetime

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(WS)

UI_FIELDS = ('title', 'subtitle', 'legend', 'unit', 'highlight', 'valueLabel')

# (正则, 替换) —— 边界用 (?<![A-Za-z])…(?![A-Za-z])，避免误伤 slug / 指标码
RULES = [
    (re.compile(r'(?<![A-Za-z])TWh(?![A-Za-z])'), '太瓦时'),
    (re.compile(r'(?<![A-Za-z])GWh(?![A-Za-z])'), '吉瓦时'),
    (re.compile(r'(?<![A-Za-z])MWh(?![A-Za-z])'), '兆瓦时'),
    (re.compile(r'(?<![A-Za-z])kWh(?![A-Za-z])'), '千瓦时'),
    (re.compile(r'(?<![A-Za-z])GDP(?![A-Za-z])'), '国内生产总值'),
    (re.compile(r'(?<![A-Za-z])ETF(?![A-Za-z])'), '指数基金'),
    (re.compile(r'(?<![A-Za-z])CPI(?![A-Za-z])'), '物价指数'),
    (re.compile(r'(?<![A-Za-z])PPI(?![A-Za-z])'), '出厂价格指数'),
    (re.compile(r'(?<![A-Za-z])Top\s?10(?![A-Za-z])'), '前十'),
    (re.compile(r'(?<![A-Za-z])Top\s?20(?![A-Za-z])'), '前二十'),
    (re.compile(r'(?<![A-Za-z])AI(?![A-Za-z])'), '人工智能'),
    (re.compile(r'\s*[vV][sS]\s*'), '对'),
    # 替换后中文词之间可能留下多余空格（如「年均 物价指数 同比涨幅」）
    (re.compile(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])'), ''),
]
# 副标题开头的内部题材编号（A2 / S10 …）——渲染时会被当成标题一部分显示
IDX_PREFIX = re.compile(r'^\s*[AS]\d{1,2}\s+')


def fix_text(s, field):
    if not s or not isinstance(s, str):
        return s, False
    orig = s
    for pat, rep in RULES:
        s = pat.sub(rep, s)
    if field == 'subtitle':
        s = IDX_PREFIX.sub('', s)
    return s, s != orig


def main():
    dry = '--dry-run' in sys.argv
    files = sorted(glob.glob('topics_registry_*.json'))
    changed_files = {}
    total = 0
    for f in files:
        try:
            data = json.load(open(f, encoding='utf-8'))
        except Exception as e:
            print('跳过 %s: %s' % (f, e))
            continue
        touched = False
        for t in data.get('topics', []):
            p = t.get('params', t)
            for k in UI_FIELDS:
                if k not in p:
                    continue
                nv, ch = fix_text(p[k], k)
                if ch:
                    if not dry:
                        p[k] = nv
                    touched = True
                    total += 1
                    key = t.get('key') or t.get('slug') or '?'
                    print('  %s :: %s.%s' % (key, k, ''))
                    print('      - %s' % p[k])
                    print('      + %s' % nv)
        if touched:
            changed_files[f] = data

    print('\n共 %d 处改动，涉及 %d 个注册表文件' % (total, len(changed_files)))
    if dry or not changed_files:
        print('(dry-run，未写入)' if dry else '(无改动)')
        return

    bdir = os.path.join('data', '_backup_registry_pre_uicn',
                        datetime.now().strftime('%Y%m%d_%H%M%S'))
    os.makedirs(bdir, exist_ok=True)
    for f in changed_files:
        shutil.copy2(f, os.path.join(bdir, os.path.basename(f)))
    for f, data in changed_files.items():
        with open(f, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    print('备份到 %s' % os.path.abspath(bdir))
    print('已写入 %d 个文件' % len(changed_files))


if __name__ == '__main__':
    main()
