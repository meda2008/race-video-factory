# -*- coding: utf-8 -*-
"""fortune_revenue 追加 2025 列（2026 财富世界 500 强，FY2025 营收，亿美元）。"""
import os

WS = 'C:/Users/medam/WorkBuddy/视频测试/batch2_ws'
p = os.path.join(WS, 'topics/fortune_revenue.csv')
vals = {
    '沃尔玛': 713.2, '国家电网': 555.4, '中国石化': 364.0, '中国石油': 401.9,
    '苹果': 416.2, '伯克希尔': 371.4, '大众汽车': 363.1, '亚马逊': 716.9,
}
lines = open(p, encoding='utf-8-sig', newline='').read().splitlines()
while lines and lines[-1].strip() == '':
    lines.pop()
header = lines[0].split(',')
assert '2025' not in header, '已有 2025 列'
header.append('2025')
out = [','.join(header)]
for ln in lines[1:]:
    cols = ln.split(',')
    nm = cols[0]
    assert nm in vals, '未找到 %s' % nm
    cols.append(str(vals[nm]))
    out.append(','.join(cols))
open(p, 'w', encoding='utf-8', newline='').write('\n'.join(out) + '\n')
print('fortune_revenue 追加 2025 完成；末行示例:', out[-1])
