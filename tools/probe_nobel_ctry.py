# -*- coding: utf-8 -*-
"""诺贝尔奖官方 API 探测：打印 2.1 版接口里所有出现过的「出生国英文名」。

用于校准 fetch_nobel.py 里的「中文国名 -> 英文国名」映射表。
"""
import json
import urllib.request
from collections import Counter

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def main():
    url = "https://api.nobelprize.org/2.1/laureates?limit=2000&sort=asc"
    req = urllib.request.Request(url, headers=UA)
    d = json.loads(urllib.request.urlopen(req, timeout=120).read())
    lau = d.get("laureates", [])
    print("laureates:", len(lau))

    keys = Counter()
    born = Counter()
    now = Counter()
    ymax = 0
    for L in lau:
        b = L.get("birth") or {}
        pl = b.get("place") or {}
        c = pl.get("country") or {}
        cn = pl.get("countryNow") or {}
        for k in pl:
            keys[k] += 1
        if c.get("en"):
            born[c["en"]] += 1
        if cn.get("en"):
            now[cn["en"]] += 1
        for p in L.get("nobelPrizes") or []:
            y = int(p.get("awardYear") or 0)
            ymax = max(ymax, y)

    print("place 字段:", dict(keys))
    print("最大 awardYear:", ymax)
    print("\n-- birth.place.country.en --")
    for k, v in born.most_common():
        print("  %-32s %d" % (k, v))
    print("\n-- birth.place.countryNow.en（仅列出与上面不同的）--")
    for k, v in now.most_common():
        if k not in born:
            print("  %-32s %d" % (k, v))


if __name__ == "__main__":
    main()
