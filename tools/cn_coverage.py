#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检查 entity_cn.cn_name() 对全部题材 CSV 首列实体名的覆盖率。

用法:
    python scripts_local/cn_coverage.py            # 列出全部未命中名（按题材数排序）
    python scripts_local/cn_coverage.py --all      # 连已命中的一起打印
"""
from __future__ import annotations

import csv
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import entity_cn  # noqa: E402

CSV_DIR = os.path.join(os.path.dirname(HERE), "data", "topics_csv")


def first_col_names(path):
    """读 CSV 首列实体名（跳过表头）。"""
    out = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        for i, row in enumerate(r):
            if i == 0 or not row:
                continue
            v = (row[0] or "").strip()
            if v:
                out.append(v)
    return out


def main():
    show_all = "--all" in sys.argv

    # name -> set(topic)
    miss = defaultdict(set)
    hit = defaultdict(set)
    keep = defaultdict(set)      # KEEP_LATIN：有意保留拉丁名
    cnok = defaultdict(set)      # 已含中文、无需处理

    for fn in sorted(os.listdir(CSV_DIR)):
        if not fn.endswith(".csv"):
            continue
        topic = fn[:-4]
        p = os.path.join(CSV_DIR, fn)
        try:
            names = first_col_names(p)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ {fn}: {e}")
            continue
        for n in names:
            base = n.split("|")[0].strip()
            # 1) 明确要保留拉丁名的
            if base in entity_cn.KEEP_LATIN:
                keep[base].add(topic)
                continue
            # 2) 已含中文且不在 STRIP_SUFFIX 里 -> 视为已是中文名
            if (re.search(r"[\u4e00-\u9fff]", base)
                    and base not in entity_cn.STRIP_SUFFIX
                    and base.split("|")[0] not in entity_cn.STRIP_SUFFIX):
                cnok[base].add(topic)
                continue
            out = entity_cn.cn_name(n)
            ob = out.split("|")[0].strip()
            if ob == base:
                miss[base].add(topic)
            else:
                hit[base].add(topic)

    tot_hit = len(hit)
    tot_miss = len(miss)
    print(f"✅ 命中 {tot_hit} 个实体名   ❌ 未命中 {tot_miss} 个"
          f"   🔤 保留拉丁 {len(keep)}   🈶 已是中文 {len(cnok)}")

    if show_all:
        for k in sorted(hit, key=lambda x: (-len(hit[x]), x)):
            print(f"  ✓ {k} -> {entity_cn.cn_name(k)}   ({len(hit[k])} 题材)")

    if miss:
        print("\n=== 未命中（按题材数排序） ===")
        for k in sorted(miss, key=lambda x: (-len(miss[x]), x)):
            print(f"{len(miss[k]):3d}  {k}")


if __name__ == "__main__":
    main()
