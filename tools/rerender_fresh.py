# -*- coding: utf-8 -*-
"""数据刷新后重渲染并保持原编号（2026-09-06 新建）。

与旧 rerender_one.py 的区别：成片现在直接落在 D:\\AI视频\\数据竞速，
编号对照表从 D:\\AI视频\\manifest.json 读，而不是 workspace 的 manifest。

流程（每个 key）：
  1. 从根清单查旧条目（编号/文件名）
  2. 把 data/topic_<key>_* 的中间产物（口播稿/时间轴/文案）move 到 _trash（不删除，
     规避 safe-delete 50 文件硬杀），强制重新生成 —— 否则时间轴锚点还停在旧末年
  3. run.py topic_config 渲染 + 直接交付到 D:\\AI视频\\数据竞速（新编号）
  4. 新片覆盖旧编号文件，删除新文件，根清单里删除新条目、刷新旧条目时间戳

用法：
  python rerender_fresh.py ashare_profit chip_revenue
  python rerender_fresh.py --from-list 需重渲染清单_2026-09-06.md
  python rerender_fresh.py --all-stale --limit 5
  python rerender_fresh.py ashare_profit --dry-run
"""
import argparse
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN = r"C:/Users/medam/.workbuddy/skills/finance-ranking-video/scripts/run.py"
PY = r"C:/Users/medam/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
ROOT_MAN = r"D:\AI视频\manifest.json"
PROJECT = "数据竞速"
TRASH = os.path.join(WS, "data", "_trash_rerender")

STALE_SUFFIX = ["_narration.txt", "_wechat_narration.txt", "_post_meta.json",
                "_wechat_post_meta.json", "_post_meta.txt", "_wechat_post_meta.txt",
                "_timeline.json"]


def load_manifest():
    return json.load(open(ROOT_MAN, encoding="utf-8"))


def save_manifest(m):
    tmp = ROOT_MAN + ".tmp"
    json.dump(m, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    os.replace(tmp, ROOT_MAN)


def find_entry(man, key):
    kind = "topic_" + key
    hit = [v for v in man.get("videos", [])
           if v.get("kind") == kind and v.get("project") == PROJECT]
    return hit[0] if hit else None


def find_registry(key):
    for p in sorted(glob.glob(os.path.join(WS, "topics_registry_*.json"))):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        for t in d.get("topics", []):
            if t.get("key") == key:
                return p
    return None


def move_stale(key):
    os.makedirs(TRASH, exist_ok=True)
    n = 0
    base = os.path.join(WS, "data", "topic_%s" % key)
    for suf in STALE_SUFFIX:
        p = base + suf
        if os.path.exists(p):
            dst = os.path.join(TRASH, os.path.basename(p))
            if os.path.exists(dst):
                dst = os.path.join(TRASH, "%d_%s" % (int(time.time() * 1000), os.path.basename(p)))
            shutil.move(p, dst)
            n += 1
    return n


def run_render(key, regp, timeout=1500):
    cmd = [PY, RUN, "topic_config", "--key", key, "--registry", regp,
           "--workspace", WS]
    out = subprocess.run(cmd, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=timeout)
    txt = (out.stdout or "") + (out.stderr or "")
    m = re.search(r"编号=(\d+)", txt)
    if not m:
        raise RuntimeError("未解析到编号；输出尾:\n" + txt[-700:])
    return m.group(1), txt


def one(key, dry=False):
    man = load_manifest()
    old = find_entry(man, key)
    if not old:
        return "SKIP: 根清单无此题材"
    regp = find_registry(key)
    if not regp:
        return "SKIP: 注册表未找到"
    old_path = old.get("dest_path") or os.path.join(r"D:\AI视频", PROJECT, old["file"])
    if not os.path.exists(old_path):
        return "SKIP: 成片不存在 " + old_path
    print("  [%s] %s  旧编号 %s" % (key, old["file"], old["no"]))
    if dry:
        return "DRY"
    n = move_stale(key)
    print("     清理中间产物 %d 个" % n)
    new_no, txt = run_render(key, regp)
    print("     新编号 %s" % new_no)

    man = load_manifest()
    new = [v for v in man.get("videos", [])
           if v.get("project") == PROJECT and v.get("no") == new_no]
    if not new:
        return "FAIL: 根清单未登记新片 %s" % new_no
    new = new[0]
    new_path = new.get("dest_path") or os.path.join(r"D:\AI视频", PROJECT, new["file"])
    if not os.path.exists(new_path):
        return "FAIL: 新片不存在 " + new_path

    # 覆盖旧编号文件（保留旧文件名与编号）
    shutil.copyfile(new_path, old_path)
    new_md = new_path[:-4] + "_发布文案.md"
    old_md = old_path[:-4] + "_发布文案.md"
    if os.path.exists(new_md):
        shutil.copyfile(new_md, old_md)
    # 清理新编号的临时产物（每支 2~3 个文件，远低于 safe-delete 阈值）
    for p in (new_path, new_md):
        if os.path.exists(p) and p not in (old_path, old_md):
            os.remove(p)
    # 根清单：删新条目、刷新旧条目（注意用 no+file 匹配，不能用 `is`——
    # 两次 load 得到的是不同对象，身份比较永远为假）
    man["videos"] = [v for v in man["videos"] if v is not new]
    for v in man["videos"]:
        if v.get("no") == old["no"] and v.get("file") == old["file"]:
            v["size_bytes"] = os.path.getsize(old_path)
            v["created_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    man["totals"]["videos"] = len(man["videos"])
    save_manifest(man)
    return "OK -> %s（覆盖）" % os.path.basename(old_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--from-list", default="", help="从 survey_rerender 生成的 md 读 key")
    ap.add_argument("--all-stale", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    keys = list(a.keys)
    if a.from_list:
        txt = open(os.path.join(WS, a.from_list), encoding="utf-8").read()
        keys += re.findall(r"^\|\s*\d+\s*\|\s*([a-z0-9_]+)\s*\|", txt, re.M)
    if a.all_stale:
        keys = []
    if a.limit:
        keys = keys[:a.limit]
    keys = list(dict.fromkeys(keys))
    print("待重渲染 %d 个：%s\n" % (len(keys), ", ".join(keys)))

    res = []
    for k in keys:
        print("===== %s =====" % k)
        try:
            r = one(k, a.dry_run)
        except Exception as e:
            r = "ERR: " + repr(e)[:200]
        print("  -> %s\n" % r)
        res.append((k, r))
    ok = sum(1 for _, r in res if r.startswith(("OK", "DRY")))
    print("完成 %d / %d" % (ok, len(res)))
    for k, r in res:
        if not r.startswith(("OK", "DRY")):
            print("  ✗ %-22s %s" % (k, r))


if __name__ == "__main__":
    main()
