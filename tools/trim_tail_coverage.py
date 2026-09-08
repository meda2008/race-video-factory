# -*- coding: utf-8 -*-
"""通用「末列覆盖率截尾」守护（2026-09-06 新建）。

问题：刷新脚本把「最新期次」追加进来时，常常只有少数公司已披露（例如美股
2026Q3 只有 2/10 家披露），末列覆盖率塌陷 → 竞速视频最后一帧大面积掉柱。

本工具从表尾往前扫：某列的有效实体占比 < max(floor, 前一列占比 × ratio)
就删除该列及其之后的所有列（因为数据一旦塌陷通常连续）。

与 check_freshness.py 的区别：那个只「报告」，这个直接「修」。

用法：
  python trim_tail_coverage.py ai_capex chip_revenue        # 修指定题材
  python trim_tail_coverage.py --scan                        # 扫全部 CSV 只报告
  python trim_tail_coverage.py --scan --fix                  # 扫全部并修复
  python trim_tail_coverage.py ai_capex --dry-run            # 只看不做
"""
import argparse
import csv
import glob
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DIRS = [os.path.join(WS, "data", "topics_csv"), os.path.join(WS, "topics")]


def resolve(key):
    for d in CSV_DIRS:
        p = os.path.join(d, key + ".csv")
        if os.path.exists(p):
            return p
    hits = glob.glob(os.path.join(WS, "**", key + ".csv"), recursive=True)
    return hits[0] if hits else None


def coverage(rows, i):
    n = 0
    for r in rows[1:]:
        if i < len(r) and (r[i] or "").strip() not in ("", "-", "--"):
            n += 1
    return n, max(1, len(rows) - 1)


def _num(s):
    try:
        v = float(str(s).replace(",", ""))
        return v
    except (TypeError, ValueError):
        return None


def topn_hit(rows, i_ref, i_new, n=15):
    """上一列 Top-N 实体在新列里仍有值的比例。

    竞速图只画 Top N（10~15）根柱子，所以真正该关心的不是「全表覆盖率」，
    而是「去年排在前面的那些国家，今年还在不在」。200+ 国的题材掉几十个小国
    完全无所谓；10 个实体的小题材掉 4 个就是灾难 —— 这个指标能自动区分两者。
    """
    vals = []
    for r in rows[1:]:
        if i_ref >= len(r):
            continue
        v = _num((r[i_ref] or "").strip())
        if v is not None:
            vals.append((r[0].strip(), v))
    if not vals:
        return 1.0
    vals.sort(key=lambda kv: -kv[1])
    top = [nm for nm, _ in vals[:n]]
    cur = {}
    for r in rows[1:]:
        if i_new < len(r):
            cur[r[0].strip()] = (r[i_new] or "").strip()
    hit = sum(1 for nm in top if cur.get(nm, "") not in ("", "-", "--"))
    return hit / len(top)


def trim(path, ratio=0.8, floor=0.45, dry=False, max_trim=8, topn=15):
    """从表尾往前扫：第 i 列相对第 i-1 列的「Top-N 命中率」低于 ratio，
    或全表覆盖率低于 floor，就删除第 i 列及之后所有列（塌陷通常连续）。"""
    rows = list(csv.reader(open(path, encoding="utf-8-sig", newline="")))
    head = rows[0]
    ncol = len(head)
    if ncol < 3:
        return None

    def cov(i):
        c, tot = coverage(rows, i)
        return c / tot

    cut = ncol
    trimmed = []
    for i in range(ncol - 1, 0, -1):
        hit = topn_hit(rows, i - 1, i, topn)
        if hit >= ratio and cov(i) >= floor:
            break
        cut = i
        trimmed.append((head[i], hit))
        if len(trimmed) >= max_trim:
            break
    if cut >= ncol:
        return None
    trimmed_names = [x[0] for x in reversed(trimmed)]
    if dry:
        hit_txt = "、".join("%s(Top%d命中%.0f%%,全表%.0f%%)"
                           % (nm, topn, h * 100, cov(ncol - j - 1) * 100)
                           for j, (nm, h) in enumerate(reversed(trimmed)))
        return ("将删除", trimmed_names, cut, hit_txt)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow(r[:cut])
    hit_txt = "、".join("%s(Top%d命中%.0f%%)" % (nm, topn, h * 100)
                       for nm, h in reversed(trimmed))
    return ("已删除", trimmed_names, cut, hit_txt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--scan", action="store_true", help="扫描全部题材 CSV")
    ap.add_argument("--fix", action="store_true", help="配合 --scan：直接修复")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ratio", type=float, default=0.8,
                    help="上一年 Top-N 实体在新末列仍需有值的比例下限")
    ap.add_argument("--floor", type=float, default=0.35,
                    help="新末列全表覆盖率绝对下限")
    ap.add_argument("--topn", type=int, default=15, help="取前 N 名作为判定集合")
    a = ap.parse_args()

    keys = a.keys
    if a.scan:
        keys = []
        for d in CSV_DIRS:
            for p in sorted(glob.glob(os.path.join(d, "*.csv"))):
                b = os.path.basename(p)[:-4]
                if b.startswith("_"):
                    continue
                keys.append(b)
        keys = sorted(set(keys))

    if not keys:
        ap.print_help()
        return 1

    n_fix = 0
    for k in keys:
        p = resolve(k)
        if not p:
            print("  ?? %-22s CSV 未找到" % k)
            continue
        r = trim(p, a.ratio, a.floor, dry=(a.dry_run or (a.scan and not a.fix)),
                 topn=a.topn)
        if not r:
            if not a.scan:
                print("  ✓ %-22s 末列覆盖率正常" % k)
            continue
        verb, cols, cut, hit = r
        n_fix += 1
        print("  %s %-18s %s %s（保留 %d 列）"
              % ("⚠" if verb == "将删除" else "✂", k, verb, hit, cut))
    print("需处理 %d 个题材" % n_fix)
    return 0


if __name__ == "__main__":
    sys.exit(main())
