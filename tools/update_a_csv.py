# -*- coding: utf-8 -*-
"""为 6 支已确认最新数据源的数据集追加新年份列（保留全部历史，绝不截断）。
数值均来自官方/权威发布，见 数据源调研_2026-09-05.md。"""
import os, io

WS = 'C:/Users/medam/WorkBuddy/视频测试/batch2_ws'

# (相对路径, 新年份, {名称(取|前): 值})
JOBS = [
    ('topics/box_office.csv', 2025, {'全国总票房': 518.32}),
    ('data/topics_csv/marriage_rate.csv', 2025, {'中国结婚率': 4.8}),
    ('topics/city_pop.csv', 2025, {
        '重庆': 3187.26, '上海': 2485.41, '北京': 2180.0, '成都': 2153.5,
        '广州': 1910.1, '深圳': 1824.85, '天津': 1363, '杭州': 1270.0}),
    ('topics/industry_salary.csv', 2025, {
        '农林牧渔': 74424, '采矿业': 143361, '制造业': 113594, '电力燃气水': 160897,
        '建筑业': 92036, '交通运输仓储邮政': 133981, '住宿餐饮': 62461, '信息传输软件': 248752,
        '批发零售': 135749, '金融业': 211164, '房地产业': 89679, '租赁商务': 110162,
        '科研技术': 182064, '水利环境': 70172, '居民服务': 70226, '教育': 133539,
        '卫生社保': 146266, '文体': 129447, '公共管理': 119465}),
    ('topics/gold_oil.csv', 2025, {'黄金': 280.1, '原油WTI': 81.4}),
    ('topics/university.csv', 2026, {
        '清华大学': 1087.1, '北京大学': 1036.3, '浙江大学': 895.6, '上海交通大学': 894.2,
        '复旦大学': 792.4, '南京大学': 708.5, '中国科学技术大学': 653.1, '武汉大学': 638.7,
        '华中科技大学': 638.0, '西安交通大学': 620.8}),
]

def base(name):
    return name.split('|')[0] if '|' in name else name

for rel, year, vals in JOBS:
    p = os.path.join(WS, rel)
    lines = open(p, encoding='utf-8-sig', newline='').read().splitlines()
    # 去掉末尾空行
    while lines and lines[-1].strip() == '':
        lines.pop()
    header = lines[0].split(',')
    assert base(header[0]) == 'name', '首列应为 name: %s' % rel
    if str(year) in header:
        print('[跳过] %s 已有 %s 列' % (rel, year)); continue
    header.append(str(year))
    out = [','.join(header)]
    for ln in lines[1:]:
        cols = ln.split(',')
        nm = cols[0]
        v = vals.get(base(nm))
        if v is None:
            raise SystemExit('[%s] 未找到 %s 的 %s 值' % (rel, nm, year))
        cols.append(repr(v) if isinstance(v, float) else str(v))
        out.append(','.join(cols))
    # 保证结尾换行
    open(p, 'w', encoding='utf-8', newline='').write('\n'.join(out) + '\n')
    print('[完成] %s -> 追加 %s；新表头末3列: %s' % (rel, year, header[-3:]))
    print('        末行示例: %s' % out[-1])
print('ALL DONE')
