# -*- coding: utf-8 -*-
"""把 deliver 新生成的编号文件，覆盖回该题材原有的编号文件，并清理 manifest 重复条目。
用法：python replace_deliver.py <key> <new_no>
例：python replace_deliver.py fx_reserves 074
（074_各国外汇储备竞速.mp4 的内容覆盖 002_各国外汇储备竞速.mp4，删除 074，manifest 去重）
"""
import argparse, json, os, glob, shutil
WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(WS, 'out', '增长与分化')
MAN = os.path.join(OUT, 'manifest.json')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('key'); ap.add_argument('new_no')
    a = ap.parse_args()
    kind = 'topic_%s' % a.key
    man = json.load(open(MAN, encoding='utf-8'))
    entries = [e for e in man if e.get('kind') == kind]
    if len(entries) < 2:
        print('未找到重复条目（kind=%s），无需替换。当前条目数=%d' % (kind, len(entries)))
        return
    new_entry = next(e for e in entries if e['file'].startswith(a.new_no + '_'))
    old_entry = next(e for e in entries if not e['file'].startswith(a.new_no + '_'))
    new_path = os.path.join(OUT, new_entry['file'])
    old_path = os.path.join(OUT, old_entry['file'])
    # 覆盖旧文件
    shutil.copyfile(new_path, old_path)
    print('覆盖 ->', old_path)
    # 发布文案同步
    new_md = os.path.join(OUT, new_entry['file'].replace('.mp4', '_发布文案.md'))
    old_md = os.path.join(OUT, old_entry['file'].replace('.mp4', '_发布文案.md'))
    if os.path.exists(new_md):
        shutil.copyfile(new_md, old_md)
        os.remove(new_md)
        print('覆盖文案 ->', old_md)
    # 删除新编号文件
    os.remove(new_path)
    print('删除 ->', new_path)
    # 清理 manifest：去掉 new_entry，更新 old_entry 时间
    man2 = [e for e in man if e is not new_entry]
    for e in man2:
        if e.get('kind') == kind and e['file'] == old_entry['file']:
            e['created_at'] = new_entry.get('created_at', e['created_at'])
    json.dump(man2, open(MAN, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('manifest 清理完成，剩余 %d 条' % len(man2))

if __name__ == '__main__':
    main()
