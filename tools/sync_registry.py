# -*- coding: utf-8 -*-
"""注册表文案 <- CSV 实际跨度/粒度 反向同步（2026-09-06 新建）。

背景：注册表里的 subtitle / legend / source 写死了年份区间和「年度」字样，
数据刷新后（尤其是年度→季度升级、或末列被覆盖率护栏截掉）文案会与实际数据
不符，观众看到的副标题就是错的。

本脚本以 **CSV 为唯一事实来源**，反向校正注册表的三处文案：
  * subtitle 的年份区间  -> 首年–末年（末年取「实际有数据的最后一列」）
  * subtitle/legend 的粒度词 -> 季度数据用「单季」，月度用「月度」，年度用「年度」
  * source 末尾的「自动刷新至 XXXX」 -> 实际末年标签

用法：
  python sync_registry.py            # 全量同步（写盘）
  python sync_registry.py --dry-run  # 只报告差异
"""
import argparse
import csv
import datetime
import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG_GLOB = os.path.join(WS, "topics_registry_*.json")

YEAR_RE = re.compile(r"(19|20)\d{2}(Q[1-4]|-\d{2})?")
RANGE_RE = re.compile(
    r"((?:19|20)\d{2}(?:Q[1-4])?)"
    r"(\s*(?:→|–|—|-|~|至)\s*)"
    r"((?:19|20)\d{2}(?:Q[1-4])?)")
REFRESH_RE = re.compile(r"[；;]?\s*自动刷新至\s*[0-9]{4}(Q[1-4]|-\d{2})?")


def last_filled_col(rows):
    """返回 (首列标签, 末列标签, 粒度)。粒度 ∈ quarter / month / year。"""
    head = [c for c in rows[0][1:] if c.strip()]
    if not head:
        return "", "", "year"
    last = head[-1]
    for i in range(len(head) - 1, -1, -1):
        n = sum(1 for r in rows[1:]
                if i + 1 < len(r) and (r[i + 1] or "").strip() not in ("", "-", "--"))
        if n >= 3:
            last = head[i]
            break
    if re.match(r"^\d{4}Q[1-4]$", str(last)):
        gran = "quarter"
    elif re.match(r"^\d{4}-\d{2}$", str(last)):
        gran = "month"
    else:
        gran = "year"
    return head[0], last, gran


GRAN_WORD = {"quarter": "单季", "month": "月度", "year": "年度"}


def fix_gran(text, gran):
    """把文案里的粒度词对齐：季度数据里出现「年度/年」改成「单季」。"""
    if gran == "year" or not text:
        return text
    out = text
    if gran == "quarter":
        out = re.sub(r"年度", "单季", out)
        out = re.sub(r"(\d{4})年(?![代])", r"\1", out)
    elif gran == "month":
        out = re.sub(r"年度", "月度", out)
    return out


def fix_range(text, first, last):
    """把年份区间的后半段替换为实际末年；无区间则不改。"""

    def _rep(m):
        return "%s%s%s" % (m.group(1), m.group(2), last)

    new, n = RANGE_RE.subn(_rep, text, count=1)
    return new


def fix_refresh(text, last):
    """只更新已有「自动刷新至 XXXX」标注的条目；人工数据题材不追加（避免误导）。"""
    if "自动刷新至" not in text:
        return text
    new = REFRESH_RE.sub("", text).rstrip("；; ")
    return new + "；自动刷新至 %s" % last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    only = {s.strip() for s in a.only.split(",") if s.strip()}

    n_topic = n_change = 0
    for p in sorted(glob.glob(REG_GLOB)):
        d = json.load(open(p, encoding="utf-8"))
        dirty = False
        n_file_change = 0
        for t in d.get("topics", []):
            key = t.get("key", "")
            if only and key not in only:
                continue
            prm = t.get("params") or {}
            rel = prm.get("path") or prm.get("csv") or ""
            if not rel:
                continue
            cpath = os.path.join(WS, rel)
            if not os.path.exists(cpath):
                continue
            rows = list(csv.reader(open(cpath, encoding="utf-8-sig", newline="")))
            if len(rows) < 2:
                continue
            n_topic += 1
            first, last, gran = last_filled_col(rows)
            item_changed = False

            for field in ("subtitle", "legend", "title"):
                old = prm.get(field) or ""
                if not old:
                    continue
                new = fix_range(old, first, last)
                if field in ("subtitle", "legend"):
                    new = fix_gran(new, gran)
                if new != old:
                    prm[field] = new
                    dirty = item_changed = True
                    print("  %-20s %-8s %s\n      %s\n      %s"
                          % (key, field, os.path.basename(p), old, new))
            old_src = prm.get("source") or ""
            if old_src:
                new_src = fix_refresh(old_src, last)
                if new_src != old_src:
                    prm["source"] = new_src
                    dirty = item_changed = True
            if item_changed:
                n_change += 1
                n_file_change += 1
        if dirty and not a.dry_run:
            json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("检查 %d 个条目，变更 %d 个%s"
          % (n_topic, n_change, "（dry-run 未写盘）" if a.dry_run else ""))


if __name__ == "__main__":
    main()
