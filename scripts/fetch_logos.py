# -*- coding: utf-8 -*-
"""下载实体的真实 logo（品牌标 / 国旗），供竞速图柱子末端徽章使用。

Windows headless Chrome 用 Segoe UI Emoji 渲染，**不支持彩色国旗 emoji**
（实测 🇺🇸 显示成「US」两个字母），emoji 也不等于品牌 logo。故改为下载真实图片：

- 品牌：优先 SimpleIcons（jsdelivr CDN，3000+ 品牌矢量 SVG，单色可着色）
        兜底 Google favicon 服务（任意域名，PNG，通用性最好）
- 国别：FlagCDN（https://flagcdn.com/w160/{iso2}.png，实测 200）

产物：assets/logos/{slug}.png，文件名只含 ASCII，便于 HTML 引用。
用法：python fetch_logos.py brand1 brand2 ...  （或 --country 中国 美国 ...）
"""
import os
import re
import sys
import urllib.parse

import requests

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(WS, 'assets', 'logos')
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/124.0 Safari/537.36'}

# 品牌 -> 域名（Google favicon 用）。SimpleIcons 的 slug 多与小写名一致，无需单独表。
DOMAINS = {
    'Apple': 'apple.com', 'Microsoft': 'microsoft.com', 'Google': 'google.com',
    'Amazon': 'amazon.com', 'Samsung': 'samsung.com', 'Toyota': 'toyota.com',
    'Mercedes-Benz': 'mercedes-benz.com', "McDonald's": 'mcdonalds.com',
    'Disney': 'disney.com', 'Nike': 'nike.com', 'BMW': 'bmw.com',
    'Louis Vuitton': 'louisvuitton.com', 'Tesla': 'tesla.com',
    'Facebook': 'facebook.com', 'Cisco': 'cisco.com', 'Intel': 'intel.com',
    'HP': 'hp.com', 'Oracle': 'oracle.com', 'SAP': 'sap.com', 'Honda': 'honda.com',
    'American Express': 'americanexpress.com', 'General Electric': 'ge.com',
    'Citigroup': 'citigroup.com', 'Gillette': 'gillette.com', 'Marlboro': 'marlboro.com',
    'Audi': 'audi.com', 'Nissan': 'nissan.com', 'Pepsi': 'pepsi.com',
    'Budweiser': 'budweiser.com', 'UPS': 'ups.com', 'FedEx': 'fedex.com',
    'JPMorgan': 'jpmorganchase.com', 'HSBC': 'hsbc.com', 'Santander': 'santander.com',
    'Goldman Sachs': 'goldmansachs.com', 'Morgan Stanley': 'morganstanley.com',
    'Adobe': 'adobe.com', 'Salesforce': 'salesforce.com', 'Netflix': 'netflix.com',
    'Uber': 'uber.com', 'Airbnb': 'airbnb.com', 'PayPal': 'paypal.com',
    'Visa': 'visa.com', 'Mastercard': 'mastercard.com', 'Target': 'target.com',
    'Costco': 'costco.com', 'Home Depot': 'homedepot.com', 'Adidas': 'adidas.com',
    'Puma': 'puma.com', 'LG': 'lg.com', 'Sony': 'sony.com', 'Canon': 'canon.com',
    'Nintendo': 'nintendo.com', 'Siemens': 'siemens.com', 'Nestle': 'nestle.com',
    'Shell': 'shell.com', 'BP': 'bp.com', 'IKEA': 'ikea.com', 'Zara': 'zara.com',
    'H&M': 'hm.com', 'Chanel': 'chanel.com', 'Gucci': 'gucci.com',
    'Hermes': 'hermes.com', 'Cartier': 'cartier.com', 'Rolex': 'rolex.com',
    'Prada': 'prada.com', 'Burberry': 'burberry.com', 'Starbucks': 'starbucks.com',
    'KFC': 'kfc.com', 'Coca-Cola': 'coca-cola.com', 'Walmart': 'walmart.com',
    '3M': '3m.com', 'AIG': 'aig.com', 'AVON': 'avon.com', 'AXA': 'axa.com',
    'Accenture': 'accenture.com', 'Huawei': 'huawei.com', 'IBM': 'ibm.com',
    'GE': 'ge.com', 'Nokia': 'nokia.com', 'Xiaomi': 'xiaomi.com',
    # 美股公司
    'Meta': 'meta.com', '英伟达': 'nvidia.com', '微软': 'microsoft.com',
    '谷歌': 'google.com', '亚马逊': 'amazon.com', '甲骨文': 'oracle.com',
    '苹果': 'apple.com', '英特尔': 'intel.com', '沃尔玛': 'walmart.com',
    '礼来': 'lilly.com', '强生': 'jnj.com', '默沙东': 'merck.com',
    '艾伯维': 'abbvie.com', '辉瑞': 'pfizer.com', '百时美施贵宝': 'bms.com',
    '安进': 'amgen.com', '吉利德': 'gilead.com', 'Moderna': 'modernatx.com',
    '应用材料': 'amat.com', '泛林集团': 'lamresearch.com', '科磊': 'kla.com',
    '洛克希德马丁': 'lockheedmartin.com', '雷神': 'rtx.com',
    '诺斯罗普格鲁曼': 'northropgrumman.com', '通用动力': 'gd.com', '波音': 'boeing.com',
    '自由港麦克莫兰': 'fcx.com', '纽蒙特': 'newmont.com', '美国铝业': 'alcoa.com',
}


def slugify(name):
    """实体名 -> ASCII 文件名。中文名用拼音/保留，这里用 quoted 形式保证唯一且合法。"""
    s = re.sub(r'[^0-9A-Za-z]+', '_', name).strip('_')
    if s:
        return s.lower()
    # 纯中文等非 ASCII：用 URL 编码的十六进制，保证文件名合法且可逆
    return 'u' + urllib.parse.quote(name, safe='').replace('%', '')[:24].lower()


def save(path, data):
    with open(path, 'wb') as f:
        f.write(data)


def fetch_brand(name, timeout=20):
    """返回 (bytes, 源) 或 None。先 SimpleIcons，再 Google favicon。"""
    slug = re.sub(r'[^a-z0-9]', '', name.lower().replace('&', ''))
    cands = []
    if slug:
        cands.append(('simpleicons',
                      f'https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{slug}.svg'))
    dom = DOMAINS.get(name)
    if dom:
        cands.append(('favicon', f'https://www.google.com/s2/favicons?domain={dom}&sz=128'))
        cands.append(('ddg', f'https://icons.duckduckgo.com/ip3/{dom}.ico'))
    for src, url in cands:
        try:
            r = requests.get(url, headers=H, timeout=timeout)
            if r.status_code == 200 and len(r.content) > 200:
                ct = r.headers.get('content-type', '')
                if 'image' in ct or url.endswith('.svg') or url.endswith('.ico'):
                    return r.content, src, ct
        except Exception:
            continue
    return None


def fetch_country(iso2, timeout=20):
    url = f'https://flagcdn.com/w160/{iso2.lower()}.png'
    try:
        r = requests.get(url, headers=H, timeout=timeout)
        if r.status_code == 200 and len(r.content) > 100:
            return r.content, 'flagcdn', r.headers.get('content-type', 'image/png')
    except Exception:
        pass
    return None


def main():
    args = sys.argv[1:]
    if not args:
        print('用法: python fetch_logos.py <品牌名...> [--country 中国:CN ...] [--from-csv <ws> <csv名...>]')
        return
    country_mode = False
    names = []
    csv_mode = False
    csv_ws = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--country':
            country_mode = True
        elif a == '--from-csv':
            csv_mode = True
            csv_ws = args[i + 1]
            i += 1
            # 其后所有参数都当作 csv 名
            names.extend(_names_from_csv(csv_ws, args[i + 1:]))
            break
        else:
            names.append(a)
        i += 1

    os.makedirs(OUT, exist_ok=True)
    ok = fail = 0
    for n in names:
        slug = slugify(n)
        if country_mode:
            iso2 = n.split(':')[-1] if ':' in n else n[:2]
            res = fetch_country(iso2)
        else:
            res = fetch_brand(n)
        if res is None:
            print(f'  [miss] {n}')
            fail += 1
            continue
        data, src, ct = res
        ext = 'svg' if 'svg' in ct else 'png'
        path = os.path.join(OUT, f'{slug}.{ext}')
        save(path, data)
        print(f'  [ok] {n} <- {src} ({len(data)}B) -> {os.path.basename(path)}')
        ok += 1
    print(f'完成：成功 {ok}，失败 {fail}；输出目录 {OUT}')


def _names_from_csv(ws, csv_names):
    """从 data/topics_csv/<name>.csv 读首列实体名。"""
    import csv as _csv
    out = []
    for cn in csv_names:
        p = os.path.join(ws, 'data', 'topics_csv', f'{cn}.csv')
        if not os.path.exists(p):
            print(f'  [warn] 无此 CSV: {p}')
            continue
        with open(p, encoding='utf-8-sig') as f:
            for row in _csv.reader(f):
                if row and row[0].strip():
                    out.append(row[0].strip())
    return out


if __name__ == '__main__':
    main()
