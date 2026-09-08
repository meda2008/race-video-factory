# -*- coding: utf-8 -*-
"""列出「成片数据已落后于 CSV」的题材（2026-09-06 新建）。

判定：CSV（或注册表）的 mtime 晚于成片文件的 mtime → 说明数据是成片之后才更新的，
成片里烧录的副标题/排名都停留在旧数据上，需要重渲染。

输出：控制台表格 + out/需重渲染清单_YYYY-MM-DD.md
"""
import csv
import datetime
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_MAN = r"D:\AI视频\manifest.json"
TODAY = datetime.date.today().isoformat()


def last_filled(rows):
    head = [c for c in rows[0][1:] if c.strip()]
    if not head:
        return ""
    for i in range(len(head) - 1, -1, -1):
        n = sum(1 for r in rows[1:]
                if i + 1 < len(r) and (r[i + 1] or "").strip() not in ("", "-", "--"))
        if n >= 3:
            return head[i]
    return head[-1]


def load_registry_map():
    """key -> (csv_rel, registry_path, subtitle)"""
    out = {}
    for p in sorted(glob.glob(os.path.join(WS, "topics_registry_*.json"))):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        for t in d.get("topics", []):
            prm = t.get("params") or {}
            out[t["key"]] = (prm.get("path") or prm.get("csv") or "", p,
                             prm.get("subtitle", ""), prm.get("title", ""))
    return out


def main():
    reg = load_registry_map()
    man = json.load(open(ROOT_MAN, encoding="utf-8"))
    vids = [v for v in man.get("videos", []) if v.get("project") == "数据竞速"]
    print("成片 %d 支，注册表题材 %d 个\n" % (len(vids), len(reg)))

    rows = []
    for v in vids:
        kind = v.get("kind", "")
        if not kind.startswith("topic_"):
            continue
        key = kind[len("topic_"):]
        dest = v.get("dest_path") or ""
        if not dest or not os.path.exists(dest):
            continue
        vmt = os.path.getmtime(dest)
        csv_rel, regp, sub, title = reg.get(key, ("", "", "", ""))
        cpath = os.path.join(WS, csv_rel) if csv_rel else ""
        if not cpath or not os.path.exists(cpath):
            continue
        cmt = os.path.getmtime(cpath)
        rmt = os.path.getmtime(regp) if regp and os.path.exists(regp) else 0
        newest = max(cmt, rmt)
        data_rows = list(csv.reader(open(cpath, encoding="utf-8-sig", newline="")))
        last = last_filled(data_rows)
        stale = newest > vmt + 60
        rows.append(dict(no=v.get("no", ""), key=key, title=title or v.get("title", ""),
                         file=os.path.basename(dest), stale=stale,
                         csv_last=last, ncol=len(data_rows[0]) - 1,
                         vtime=datetime.datetime.fromtimestamp(vmt).strftime("%m-%d %H:%M"),
                         dtime=datetime.datetime.fromtimestamp(newest).strftime("%m-%d %H:%M"),
                         sub=sub))

    need = [r for r in rows if r["stale"]]
    print("== 数据已更新、需重渲染：%d 支 ==" % len(need))
    for r in sorted(need, key=lambda x: x["no"]):
        print("  %s  %-22s CSV末年=%-9s 列=%-3d 片%s 数据%s  %s"
              % (r["no"], r["key"], r["csv_last"], r["ncol"], r["vtime"], r["dtime"],
                 r["sub"][:34]))
    print("\n== 已是最新：%d 支 ==" % (len(rows) - len(need)))

    md = os.path.join(WS, "需重渲染清单_%s.md" % TODAY)
    with open(md, "w", encoding="utf-8") as f:
        f.write("# 需重渲染清单（%s）\n\n判据：CSV / 注册表 mtime 晚于成片 mtime。\n\n"
                % TODAY)
        f.write("| 编号 | key | 标题 | CSV末年 | 列数 | 成片时间 | 数据时间 |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for r in sorted(need, key=lambda x: x["no"]):
            f.write("| %s | %s | %s | %s | %d | %s | %s |\n"
                    % (r["no"], r["key"], r["title"], r["csv_last"], r["ncol"],
                       r["vtime"], r["dtime"]))
    print("\n写出", md)


if __name__ == "__main__":
    main()
