#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把题材 CSV 首列实体名批量改成中文显示名。

用法:
    python scripts_local/apply_entity_cn.py --dry-run        # 只看会改什么
    python scripts_local/apply_entity_cn.py                  # 实际改写（自动备份到 _backup_csv_pre_cn）
    python scripts_local/apply_entity_cn.py --only a b c     # 只处理指定题材

要点:
  * 只改首列的「名称段」，保留 "|代码" 后缀（A股/ETF 靠代码回查数据）
  * 已含中文 / KEEP_LATIN 的实体不动
  * 改写前整目录备份一次，备份目录 _backup_csv_pre_cn/<时间戳>/
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import entity_cn  # noqa: E402

CSV_DIR = os.path.join(ROOT, "data", "topics_csv")
BACKUP_ROOT = os.path.join(ROOT, "data", "_backup_csv_pre_cn")


def convert_file(path, dry=False):
    """改写单个 CSV 首列，返回 (是否变更, 变更明细 list[(旧,新)])."""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return False, []

    changed = []
    for i, row in enumerate(rows):
        if i == 0 or not row:
            continue
        old = row[0]
        new = entity_cn.cn_name(old)
        if new != old:
            changed.append((old, new))
            row[0] = new

    if changed and not dry:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows(rows)
    return bool(changed), changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", nargs="*", default=None,
                    help="只处理指定题材（不带 .csv 后缀）")
    ap.add_argument("--csv-dir", default=CSV_DIR)
    args = ap.parse_args()

    csv_dir = args.csv_dir
    files = sorted(f for f in os.listdir(csv_dir) if f.endswith(".csv"))
    if args.only:
        want = set(args.only)
        files = [f for f in files
                 if f[:-4] in want or f[:-4].replace(".csv", "") in want]

    # 先干跑一遍，确定要改哪些文件，只备份这些
    plan = []
    for fn in files:
        ok, ch = convert_file(os.path.join(csv_dir, fn), dry=True)
        if ok:
            plan.append((fn, ch))

    if not plan:
        print("没有需要改写的 CSV（全部已是中文名）")
        return

    tot = sum(len(c) for _, c in plan)
    print(f"将改写 {len(plan)} 个 CSV、{tot} 个实体名"
          f"{'（dry-run，未落盘）' if args.dry_run else ''}\n")

    if not args.dry_run:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        bdir = os.path.join(BACKUP_ROOT, stamp)
        os.makedirs(bdir, exist_ok=True)
        for fn, _ in plan:
            shutil.copy2(os.path.join(csv_dir, fn), os.path.join(bdir, fn))
        print(f"📦 已备份到 {bdir}\n")

    for fn, ch in plan:
        if not args.dry_run:
            convert_file(os.path.join(csv_dir, fn), dry=False)
        print(f"── {fn}  ({len(ch)} 项)")
        for old, new in ch[:8]:
            print(f"     {old}  →  {new}")
        if len(ch) > 8:
            print(f"     … 其余 {len(ch) - 8} 项")

    if not args.dry_run:
        cnt = Counter()
        for _, ch in plan:
            for o, n in ch:
                cnt[(o.split("|")[0], n.split("|")[0])] += 1
        print(f"\n✅ 完成：{len(plan)} 个 CSV、{tot} 处改名")


if __name__ == "__main__":
    main()
