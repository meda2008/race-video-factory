# -*- coding: utf-8 -*-
"""数据项（实体）名称中文化 —— 统一映射表（2026-09-06 新建）。

竞速图柱子上的标签必须让中文观众一眼看懂，所以：
  * 国家/地区/国际组织 -> 标准中文名（含 OWID 与世行 WDI 两套命名）
  * 企业/品牌        -> 中文通用译名（无通用译名的保留拉丁品牌名，见 KEEP_LATIN）
  * 聚合体/收入组    -> 中文（「高收入国家」「欧盟」「撒哈拉以南非洲」…）

用法：
    from entity_cn import cn_name
    cn_name("United States")            -> '美国'
    cn_name("沪深300ETF华泰柏瑞|510300")  -> '沪深300ETF华泰柏瑞|510300'（code 段保留）
"""
import re

# ───────────────────────── 国家 / 地区 ─────────────────────────
COUNTRY_CN = {
    # —— 主要国家 ——
    "China": "中国", "United States": "美国", "United States of America": "美国",
    "Japan": "日本", "Germany": "德国", "India": "印度", "United Kingdom": "英国",
    "France": "法国", "Italy": "意大利", "Brazil": "巴西", "Canada": "加拿大",
    "Russia": "俄罗斯", "Russian Federation": "俄罗斯", "South Korea": "韩国",
    "Korea": "韩国", "Korea, Rep.": "韩国", "Republic of Korea": "韩国",
    "Australia": "澳大利亚", "Spain": "西班牙", "Mexico": "墨西哥",
    "Indonesia": "印度尼西亚", "Netherlands": "荷兰", "Saudi Arabia": "沙特阿拉伯",
    "Turkey": "土耳其", "Turkiye": "土耳其", "Türkiye": "土耳其",
    "Switzerland": "瑞士", "Poland": "波兰", "Argentina": "阿根廷",
    "Sweden": "瑞典", "Belgium": "比利时", "Iran": "伊朗", "Iran, Islamic Rep.": "伊朗",
    "Thailand": "泰国", "Austria": "奥地利", "Nigeria": "尼日利亚",
    "Norway": "挪威", "Israel": "以色列", "Ireland": "爱尔兰",
    "United Arab Emirates": "阿联酋", "Egypt": "埃及", "Egypt, Arab Rep.": "埃及",
    "Singapore": "新加坡", "Malaysia": "马来西亚", "Vietnam": "越南",
    "Philippines": "菲律宾", "Bangladesh": "孟加拉国", "Pakistan": "巴基斯坦",
    "Chile": "智利", "Finland": "芬兰", "Portugal": "葡萄牙", "Greece": "希腊",
    "Czechia": "捷克", "Czech Republic": "捷克", "Czech Rep.": "捷克",
    "Denmark": "丹麦", "Hungary": "匈牙利", "New Zealand": "新西兰",
    "Ukraine": "乌克兰", "Kazakhstan": "哈萨克斯坦", "South Africa": "南非",
    "Colombia": "哥伦比亚", "Peru": "秘鲁", "Romania": "罗马尼亚",
    "Uzbekistan": "乌兹别克斯坦", "Qatar": "卡塔尔", "Kuwait": "科威特",
    "Morocco": "摩洛哥", "Slovakia": "斯洛伐克", "Slovak Republic": "斯洛伐克",
    "Ecuador": "厄瓜多尔", "Belarus": "白俄罗斯", "Dominican Republic": "多米尼加",
    "Guatemala": "危地马拉", "Bulgaria": "保加利亚", "Croatia": "克罗地亚",
    "Serbia": "塞尔维亚", "Luxembourg": "卢森堡", "Slovenia": "斯洛文尼亚",
    "Lithuania": "立陶宛", "Latvia": "拉脱维亚", "Estonia": "爱沙尼亚",
    "Tunisia": "突尼斯", "Jordan": "约旦", "Lebanon": "黎巴嫩",
    "Sri Lanka": "斯里兰卡", "Myanmar": "缅甸", "Burma": "缅甸",
    "Kenya": "肯尼亚", "Ethiopia": "埃塞俄比亚", "Ghana": "加纳",
    "Tanzania": "坦桑尼亚", "Uganda": "乌干达", "Angola": "安哥拉",
    "Mozambique": "莫桑比克", "Zimbabwe": "津巴布韦", "Zambia": "赞比亚",
    "Namibia": "纳米比亚", "Botswana": "博茨瓦纳", "Senegal": "塞内加尔",
    "Cameroon": "喀麦隆", "Cote d'Ivoire": "科特迪瓦", "Côte d'Ivoire": "科特迪瓦",
    "Cote dIvoire": "科特迪瓦", "Niger": "尼日尔", "Mali": "马里",
    "Burkina Faso": "布基纳法索", "Chad": "乍得", "Somalia": "索马里",
    "Sudan": "苏丹", "Libya": "利比亚", "Algeria": "阿尔及利亚",
    "Iraq": "伊拉克", "Afghanistan": "阿富汗", "Yemen": "也门", "Yemen, Rep.": "也门",
    "Syria": "叙利亚", "Nepal": "尼泊尔", "Cambodia": "柬埔寨",
    "Laos": "老挝", "Lao PDR": "老挝", "Mongolia": "蒙古",
    "North Korea": "朝鲜", "Korea, Dem. People's Rep.": "朝鲜",
    "Democratic People's Republic of Korea": "朝鲜",
    "Taiwan": "中国台湾", "Hong Kong": "中国香港", "Hong Kong SAR, China": "中国香港",
    "Macao": "中国澳门", "Macao SAR, China": "中国澳门", "Macau": "中国澳门",
    "Turkmenistan": "土库曼斯坦", "Kyrgyzstan": "吉尔吉斯斯坦",
    "Kyrgyz Republic": "吉尔吉斯斯坦", "Tajikistan": "塔吉克斯坦",
    "Armenia": "亚美尼亚", "Azerbaijan": "阿塞拜疆", "Georgia": "格鲁吉亚",
    "Moldova": "摩尔多瓦", "Albania": "阿尔巴尼亚",
    "North Macedonia": "北马其顿", "Macedonia": "北马其顿",
    "Bosnia and Herzegovina": "波黑", "Montenegro": "黑山",
    "Cyprus": "塞浦路斯", "Malta": "马耳他", "Iceland": "冰岛",
    "Uruguay": "乌拉圭", "Paraguay": "巴拉圭", "Bolivia": "玻利维亚",
    "Venezuela": "委内瑞拉", "Venezuela, RB": "委内瑞拉",
    "Costa Rica": "哥斯达黎加", "Panama": "巴拿马", "Cuba": "古巴",
    "Haiti": "海地", "Nicaragua": "尼加拉瓜", "Honduras": "洪都拉斯",
    "El Salvador": "萨尔瓦多", "Jamaica": "牙买加",
    "Trinidad and Tobago": "特立尼达和多巴哥",
    "Papua New Guinea": "巴布亚新几内亚", "Brunei": "文莱",
    "Timor-Leste": "东帝汶", "Timor": "东帝汶", "East Timor": "东帝汶",
    "Bhutan": "不丹", "Maldives": "马尔代夫", "Fiji": "斐济",
    "Guyana": "圭亚那", "Suriname": "苏里南", "Mongolia (country)": "蒙古",

    # —— 小国 / 岛国 / 属地 ——
    "Antigua and Barbuda": "安提瓜和巴布达", "Belize": "伯利兹",
    "Mauritius": "毛里求斯", "Seychelles": "塞舌尔", "Samoa": "萨摩亚",
    "Djibouti": "吉布提", "Togo": "多哥", "Solomon Islands": "所罗门群岛",
    "Tonga": "汤加", "Kiribati": "基里巴斯", "Eswatini": "埃斯瓦蒂尼",
    "Lesotho": "莱索托", "Liberia": "利比里亚", "Barbados": "巴巴多斯",
    "Sierra Leone": "塞拉利昂", "Guinea-Bissau": "几内亚比绍", "Guinea": "几内亚",
    "Burundi": "布隆迪", "Rwanda": "卢旺达", "Bahamas": "巴哈马",
    "Bahamas, The": "巴哈马", "Aruba": "阿鲁巴", "Vanuatu": "瓦努阿图",
    "Central African Republic": "中非", "Comoros": "科摩罗",
    "Sao Tome and Principe": "圣多美和普林西比", "Gambia": "冈比亚",
    "Gambia, The": "冈比亚", "Cape Verde": "佛得角", "Cabo Verde": "佛得角",
    "Saint Lucia": "圣卢西亚", "St. Lucia": "圣卢西亚", "Grenada": "格林纳达",
    "Saint Kitts and Nevis": "圣基茨和尼维斯", "St. Kitts and Nevis": "圣基茨和尼维斯",
    "Saint Vincent and the Grenadines": "圣文森特和格林纳丁斯",
    "St. Vincent and the Grenadines": "圣文森特和格林纳丁斯",
    "American Samoa": "美属萨摩亚", "French Polynesia": "法属波利尼西亚",
    "Greenland": "格陵兰", "Bermuda": "百慕大", "Nauru": "瑙鲁", "Naoero": "瑙鲁",
    "Cook Islands": "库克群岛", "Guam": "关岛", "New Caledonia": "新喀里多尼亚",
    "Turks and Caicos Islands": "特克斯和凯科斯群岛",
    "Micronesia (country)": "密克罗尼西亚", "Micronesia, Fed. Sts.": "密克罗尼西亚",
    "Dominica": "多米尼克", "Montserrat": "蒙特塞拉特", "Tuvalu": "图瓦卢",
    "Niue": "纽埃", "Marshall Islands": "马绍尔群岛", "Kosovo": "科索沃",
    "Puerto Rico": "波多黎各", "Cayman Islands": "开曼群岛", "Andorra": "安道尔",
    "Monaco": "摩纳哥", "San Marino": "圣马力诺", "Liechtenstein": "列支敦士登",
    "Vatican": "梵蒂冈", "Vatican City": "梵蒂冈", "Gibraltar": "直布罗陀",
    "Malawi": "马拉维", "Benin": "贝宁", "Guinea-Bissau (country)": "几内亚比绍",
    "Mauritania": "毛里塔尼亚", "Gabon": "加蓬", "Congo": "刚果（布）",
    "Congo, Rep.": "刚果（布）", "Congo, Dem. Rep.": "刚果（金）",
    "Democratic Republic of Congo": "刚果（金）", "South Sudan": "南苏丹",
    "Svalbard and Jan Mayen": "斯瓦尔巴和扬马延", "Western Sahara": "西撒哈拉",
    "Mayotte": "马约特", "Reunion": "留尼汪", "Réunion": "留尼汪",
    "Guadeloupe": "瓜德罗普", "Martinique": "马提尼克",
    "French Guiana": "法属圭亚那", "Curacao": "库拉索", "Curaçao": "库拉索",
    "Saint Martin (French part)": "圣马丁（法属）", "St. Martin (French part)": "圣马丁（法属）",
    "Sint Maarten (Dutch part)": "荷属圣马丁", "Saint Barthelemy": "圣巴泰勒米",
    "Saint Helena": "圣赫勒拿", "Tokelau": "托克劳",
    "Wallis and Futuna": "瓦利斯和富图纳", "Falkland Islands": "福克兰群岛",
    "Falkland Islands (Malvinas)": "福克兰群岛（马尔维纳斯）",
    "Isle of Man": "马恩岛", "Channel Islands": "海峡群岛",
    "Guernsey": "根西岛", "Jersey": "泽西岛", "Faroe Islands": "法罗群岛",
    "Faeroe Islands": "法罗群岛", "Christmas Island": "圣诞岛",
    "Virgin Islands (U.S.)": "美属维尔京群岛",
    "United States Virgin Islands": "美属维尔京群岛",
    "British Virgin Islands": "英属维尔京群岛",
    "Northern Mariana Islands": "北马里亚纳群岛",
    "Palestine": "巴勒斯坦", "West Bank and Gaza": "约旦河西岸与加沙",
    "Palau": "帕劳", "Equatorial Guinea": "赤道几内亚",
    "Eritrea": "厄立特里亚", "Madagascar": "马达加斯加",
    "Saint Kitts and Nevis (country)": "圣基茨和尼维斯",
    "Cayman Islands (country)": "开曼群岛",
    "Turks and Caicos Islands (country)": "特克斯和凯科斯群岛",
    "Sint Maarten": "荷属圣马丁", "Saint Martin": "圣马丁",
    "Micronesia": "密克罗尼西亚", "Solomon Islands (country)": "所罗门群岛",
    "Cape Verde (country)": "佛得角", "Timor-Leste (country)": "东帝汶",

    # —— 历史国家 / 已消失实体 ——
    "USSR": "苏联", "Soviet Union": "苏联", "Russian Empire": "俄罗斯帝国",
    "East Germany": "东德", "West Germany": "西德", "Yugoslavia": "南斯拉夫",
    "Czechoslovakia": "捷克斯洛伐克", "Serbia and Montenegro": "塞尔维亚和黑山",
    "Netherlands Antilles": "荷属安的列斯", "Zaire": "扎伊尔",
    "Rhodesia": "罗得西亚", "Persia": "波斯", "Siam": "暹罗",
    "Sudan (former)": "苏丹（原）", "Prussia": "普鲁士",
    "Austria-Hungary": "奥匈帝国", "Ottoman Empire": "奥斯曼帝国",
    "British India": "英属印度", "Korea (the Republic of)": "韩国",
    # ── 补全（2026-09-06 扫描漏网）──
    "Bahrain": "巴林", "Oman": "阿曼", "Brunei Darussalam": "文莱",
    "Brunei": "文莱", "Syrian Arab Republic": "叙利亚",
    "Viet Nam": "越南", "Somalia, Fed. Rep.": "索马里",
    "Saint Pierre and Miquelon": "圣皮埃尔和密克隆",
    "Anguilla": "安圭拉", "Puerto Rico (US)": "波多黎各",
    "Bonaire Sint Eustatius and Saba": "博奈尔、圣尤斯特歇斯和萨巴",
}

# ───────────────────────── 聚合体 / 收入组 / 大洲 ─────────────────────────
AGG_CN = {
    "World": "世界", "Africa": "非洲", "Asia": "亚洲", "Europe": "欧洲",
    "North America": "北美洲", "South America": "南美洲", "Oceania": "大洋洲",
    "Antarctica": "南极洲",
    "European Union (27)": "欧盟", "European Union (28)": "欧盟",
    "European Union": "欧盟", "Euro area": "欧元区",
    "High-income countries": "高收入国家", "Low-income countries": "低收入国家",
    "Lower-middle-income countries": "中低收入国家",
    "Upper-middle-income countries": "中高收入国家",
    "Middle income": "中等收入国家", "Low & middle income": "中低收入国家",
    "Low and middle income": "中低收入国家",
    "OECD members": "经合组织成员",
    "IDA & IBRD total": "国际开发协会与世行合计",
    "IDA and IBRD total": "国际开发协会与世行合计",
    "IBRD only": "仅世行贷款国", "IDA only": "仅开发协会国",
    "IDA total": "开发协会合计", "Arab World": "阿拉伯国家",
    "Caribbean small states": "加勒比小国",
    "Central Europe and the Baltics": "中欧与波罗的海",
    "Early-demographic dividend": "人口红利前期",
    "Late-demographic dividend": "人口红利后期",
    "Post-demographic dividend": "人口红利后期",
    "Pre-demographic dividend": "人口红利前期",
    "East Asia & Pacific": "东亚与太平洋",
    "East Asia and Pacific": "东亚与太平洋",
    "East Asia & Pacific (excluding high income)": "东亚与太平洋（不含高收入）",
    "Europe & Central Asia": "欧洲与中亚",
    "Europe and Central Asia": "欧洲与中亚",
    "Europe & Central Asia (excluding high income)": "欧洲与中亚（不含高收入）",
    "Latin America & Caribbean": "拉美与加勒比",
    "Latin America and Caribbean": "拉美与加勒比",
    "Latin America & the Caribbean": "拉美与加勒比",
    "Latin America & Caribbean (excluding high income)": "拉美与加勒比（不含高收入）",
    "Middle East & North Africa": "中东与北非",
    "Middle East and North Africa": "中东与北非",
    "Middle East & North Africa (excluding high income)": "中东与北非（不含高收入）",
    "Sub-Saharan Africa": "撒哈拉以南非洲",
    "Sub-Saharan Africa (excluding high income)": "撒哈拉以南非洲（不含高收入）",
    "North America (excluding high income)": "北美（不含高收入）",
    "Fragile and conflict affected situations": "脆弱与冲突地区",
    "Least developed countries: UN classification": "最不发达国家",
    "Small states": "小国", "Other small states": "其他小国",
    "Pacific island small states": "太平洋岛国",
    "Not classified": "未分类",
    "Heavily indebted poor countries (HIPC)": "重债穷国",
    "High income: OECD": "高收入：经合组织",
    "High income: nonOECD": "高收入：非经合组织",
    "Low & middle income: excluding China": "中低收入：不含中国",
    "Africa Eastern and Southern": "东部与南部非洲",
    "Africa Western and Central": "西部与中部非洲",
    "Africa Eastern and Southern (excluding high income)": "东部与南部非洲（不含高收入）",
    "Africa Western and Central (excluding high income)": "西部与中部非洲（不含高收入）",
    "Central African Republic (country)": "中非",
    "European Union (27) (country)": "欧盟",
    # ── 补全（2026-09-06 扫描漏网）──
    "South Asia": "南亚",
    "Middle East, North Africa, Afghanistan & Pakistan": "中东、北非、阿富汗与巴基斯坦",
    "Middle East, North Africa, Afghanistan & Pakistan (IDA & IBRD)": "中东、北非、阿富汗与巴基斯坦（IDA&IBRD）",
    "Middle East, North Africa, Afghanistan & Pakistan (excluding high income)": "中东、北非、阿富汗与巴基斯坦（不含高收入）",
    "South Asia (IDA & IBRD)": "南亚（IDA&IBRD）",
    "East Asia & Pacific (IDA & IBRD countries)": "东亚与太平洋（IDA&IBRD）",
    "Europe & Central Asia (IDA & IBRD countries)": "欧洲与中亚（IDA&IBRD）",
    "Latin America & the Caribbean (IDA & IBRD countries)": "拉美与加勒比（IDA&IBRD）",
    "Sub-Saharan Africa (IDA & IBRD countries)": "撒哈拉以南非洲（IDA&IBRD）",
    "IDA blend": "IDA混合型", "IDA total": "IDA合计", "IDA only": "IDA专属",
    "Africa (WHO)": "非洲（世卫组织）", "Americas (WHO)": "美洲（世卫组织）",
    "Europe (WHO)": "欧洲（世卫组织）",
    "Eastern Mediterranean (WHO)": "东地中海（世卫组织）",
    "South-East Asia (WHO)": "东南亚（世卫组织）",
    "Western Pacific (WHO)": "西太平洋（世卫组织）",
}

# ───────────────────────── 企业 / 品牌 ─────────────────────────
COMPANY_CN = {
    # 科技巨头
    "Apple": "苹果", "Microsoft": "微软", "Google": "谷歌", "Alphabet": "谷歌",
    "Amazon": "亚马逊", "Meta": "脸书", "Facebook": "脸书", "Nvidia": "英伟达",
    "NVDA": "英伟达", "Tesla": "特斯拉", "Intel": "英特尔", "IBM": "IBM",
    "Oracle": "甲骨文", "SAP": "SAP", "Salesforce": "赛富时",
    "Adobe": "奥多比", "Netflix": "奈飞", "Uber": "优步", "Airbnb": "爱彼迎",
    "Sony": "索尼", "Samsung": "三星", "Samsung Electronics": "三星电子",
    "LG": "LG", "Panasonic": "松下", "Hitachi": "日立", "Toshiba": "东芝",
    "Toyota": "丰田", "Honda": "本田", "Nissan": "日产",
    "Mercedes-Benz": "梅赛德斯-奔驰", "BMW": "宝马", "Audi": "奥迪",
    "Volkswagen": "大众", "Porsche": "保时捷", "Ford": "福特",
    "General Motors": "通用汽车", "Hyundai": "现代", "Kia": "起亚",
    "Boeing": "波音", "Airbus": "空客",
    # 半导体
    "AMD": "超威", "Qualcomm": "高通", "Broadcom": "博通", "Micron": "美光",
    "Marvell": "迈威尔", "Analog Devices": "亚德诺", "NXP": "恩智浦",
    "Texas Instruments": "德州仪器", "TSMC": "台积电", "TSM": "台积电",
    "ASML": "阿斯麦", "Applied Materials": "应用材料", "Lam Research": "泛林集团",
    "KLA": "科磊", "Teradyne": "泰瑞达", "ASML Holding": "阿斯麦",
    "Axcelis": "艾克利斯", "Cohu": "科休", "Onto Innovation": "昂图创新",
    "FormFactor": "福姆法克特", "MKS": "万机仪器", "MKS Instruments": "万机仪器",
    "Advanced Energy": "先进能源", "Aehr Test Systems": "艾尔测试系统",
    "Nova": "诺华测量", "Camtek": "康钛克",
    # 医药
    "Eli Lilly": "礼来", "Johnson & Johnson": "强生", "Merck": "默沙东",
    "AbbVie": "艾伯维", "Pfizer": "辉瑞", "Bristol-Myers Squibb": "百时美施贵宝",
    "Amgen": "安进", "Gilead": "吉利德", "Viatris": "晖致", "Moderna": "莫德纳",
    "Novartis": "诺华", "Roche": "罗氏", "AstraZeneca": "阿斯利康",
    "Sanofi": "赛诺菲", "GSK": "葛兰素史克", "GlaxoSmithKline": "葛兰素史克",
    "Novo Nordisk": "诺和诺德",
    # 军工 / 防务
    "Lockheed Martin": "洛克希德马丁", "Raytheon": "雷神", "RTX": "雷神",
    "Northrop Grumman": "诺斯罗普格鲁曼", "General Dynamics": "通用动力",
    "L3Harris": "L3哈里斯", "Huntington Ingalls": "亨廷顿英格尔斯",
    "Textron": "德事隆", "Leidos": "莱多斯", "Booz Allen": "博思艾伦",
    "BAE Systems": "英国宇航系统", "Thales": "泰雷兹",
    # 矿业 / 能源
    "Freeport-McMoRan": "自由港麦克莫兰", "Newmont": "纽蒙特",
    "Southern Copper": "南方铜业", "Cleveland-Cliffs": "克利夫兰克利夫斯",
    "United States Steel": "美国钢铁", "Alcoa": "美国铝业",
    "Mosaic": "美盛", "CF Industries": "CF工业", "MP Materials": "MP材料",
    "Hecla Mining": "赫克拉矿业", "BHP": "必和必拓", "Rio Tinto": "力拓",
    "Vale": "淡水河谷", "Anglo American": "英美资源", "Glencore": "嘉能可",
    "ExxonMobil": "埃克森美孚", "Chevron": "雪佛龙", "Shell": "壳牌",
    "BP": "英国石油", "TotalEnergies": "道达尔能源", "ConocoPhillips": "康菲石油",
    # 金融 / 消费 / 其他
    "Berkshire Hathaway": "伯克希尔哈撒韦", "JPMorgan Chase": "摩根大通",
    "Bank of America": "美国银行", "Wells Fargo": "富国银行",
    "Goldman Sachs": "高盛", "Morgan Stanley": "摩根士丹利", "Citi": "花旗",
    "Visa": "维萨", "Mastercard": "万事达", "PayPal": "贝宝",
    "Walmart": "沃尔玛", "Costco": "好市多", "Target": "塔吉特",
    "Home Depot": "家得宝", "McDonald's": "麦当劳", "Starbucks": "星巴克",
    "Nike": "耐克", "Adidas": "阿迪达斯", "Coca-Cola": "可口可乐",
    "PepsiCo": "百事", "Pepsi": "百事", "Unilever": "联合利华",
    "Nestle": "雀巢", "Nestlé": "雀巢", "Procter & Gamble": "宝洁",
    "L'Oreal": "欧莱雅", "Louis Vuitton": "路易威登", "Hermes": "爱马仕",
    "Chanel": "香奈儿", "Gucci": "古驰", "Zara": "飒拉", "H&M": "海恩斯莫里斯",
    "IKEA": "宜家", "Disney": "迪士尼", "Comcast": "康卡斯特",
    "AT&T": "美国电话电报", "Verizon": "威瑞森", "T-Mobile": "T-Mobile",
    "Deutsche Telekom": "德国电信", "Vodafone": "沃达丰",
    "Accenture": "埃森哲", "Deloitte": "德勤", "Infosys": "印孚瑟斯",
    "Allianz": "安联", "AXA": "安盛", "Zurich": "苏黎世保险",
    "AIG": "美国国际集团", "Citi": "花旗", "HSBC": "汇丰",
    "Siemens": "西门子", "BASF": "巴斯夫", "Bayer": "拜耳",
    "Dow": "陶氏", "DuPont": "杜邦", "3M": "3M",
    "Caterpillar": "卡特彼勒", "Honeywell": "霍尼韦尔", "GE": "通用电气",
    "General Electric": "通用电气", "UPS": "联合包裹", "FedEx": "联邦快递",
    # 电池 / 新能源
    "CATL": "宁德时代", "BYD": "比亚迪", "LG Energy Solution": "LG新能源",
    "LG新能源": "LG新能源", "三星SDI": "三星SDI", "SK On": "SK安",
    "SK Innovation": "SK创新", "Panasonic Energy": "松下能源",
    "CALB": "中创新航", "Gotion High-tech": "国轩高科", "EVE Energy": "亿纬锂能",
    "Sunwoda": "欣旺达", "Farasis": "孚能科技",
    # 手机
    "vivo": "维沃", "OPPO": "欧珀", "Xiaomi": "小米", "Huawei": "华为",
    "Honor": "荣耀", "Realme": "真我", "OnePlus": "一加", "Motorola": "摩托罗拉",
    "Nothing": "Nothing", "Transsion": "传音",
    # 其他在榜品牌（Interbrand 历年百强）
    "AVON": "雅芳", "Amazon.com": "亚马逊", "American Express": "美国运通",
    "Apple Inc": "苹果", "Hewlett-Packard": "惠普", "HP": "惠普",
    "Kellogg's": "家乐氏", "Budweiser": "百威", "Harley-Davidson": "哈雷戴维森",
    "Jack Daniel's": "杰克丹尼", "Heinz": "亨氏", "Colgate": "高露洁",
    "Gillette": "吉列", "Kleenex": "舒洁", "Nescafe": "雀巢咖啡",
    "Danone": "达能", "Kraft": "卡夫", "Philips": "飞利浦", "Nintendo": "任天堂",
    "KFC": "肯德基", "Pizza Hut": "必胜客", "Subway": "赛百味",
    "Corona": "科罗娜", "Heineken": "喜力", "Guinness": "健力士",
    "Smirnoff": "斯米尔诺夫", "Moet & Chandon": "酩悦香槟",
    "Johnnie Walker": "尊尼获加", "Ferrari": "法拉利", "Lamborghini": "兰博基尼",
    "IWC": "万国表", "Rolex": "劳力士", "Cartier": "卡地亚",
    "Tiffany": "蒂芙尼", "Prada": "普拉达", "Burberry": "博柏利",
    "Hugo Boss": "雨果博斯", "Ralph Lauren": "拉夫劳伦",
    "Nissan (car)": "日产", "Lego": "乐高", "Barbie": "芭比",
    "Bloomberg": "彭博", "Thomson Reuters": "汤森路透",
    "Moody's": "穆迪", "S&P": "标普", "McKinsey": "麦肯锡", "BCG": "波士顿咨询",
    "KPMG": "毕马威", "PwC": "普华永道", "EY": "安永",
    # ── 补全（2026-09-06 扫描漏网）──
    "Cisco": "思科", "Citigroup": "花旗集团", "Citibank": "花旗银行",
    "J.P. Morgan": "摩根大通", "Merrill Lynch": "美林证券",
    "Barclays": "巴克莱", "Credit Suisse": "瑞信", "UBS": "瑞银",
    "Santander": "桑坦德银行", "ING": "荷兰国际集团",
    "ThyssenKrupp": "蒂森克虏伯", "Marlboro": "万宝路", "Nokia": "诺基亚",
    "BlackBerry": "黑莓", "Burger King": "汉堡王", "Campbell's": "金宝汤",
    "Canon": "佳能", "Chevrolet": "雪佛兰", "Subaru": "斯巴鲁",
    "Lexus": "雷克萨斯", "Land Rover": "路虎", "MINI": "迷你",
    "VW (Volkswagen)": "大众", "Volkswagen": "大众",
    "Colgate-Palmolive Company": "高露洁棕榄", "Colgate": "高露洁",
    "Deere & Company": "约翰迪尔", "John Deere": "约翰迪尔",
    "Dell EMC": "戴尔EMC", "Dell Technologies": "戴尔科技",
    "Hewlett Packard Enterprise": "慧与", "Eastman Kodak": "柯达",
    "Kodak": "柯达", "Xerox": "施乐", "Lenovo": "联想", "HTC": "宏达电",
    "Dior": "迪奥", "Giorgio Armani": "乔治·阿玛尼",
    "Hermes Paris": "爱马仕", "Hennessy": "轩尼诗",
    "Moët et Chandon": "酩悦香槟", "L'Oréal": "欧莱雅",
    "Lancôme": "兰蔻", "Sephora": "丝芙兰", "Nivea": "妮维雅",
    "Tiffany & Co": "蒂芙尼", "Puma": "彪马", "GAP": "盖璞",
    "Hertz": "赫兹", "Marriott International": "万豪",
    "Duracell": "金霸王", "Pampers": "帮宝适", "Wrigley": "箭牌",
    "Nescafé": "雀巢咖啡", "Sprite": "雪碧",
    "Kentucky Fried Chicken": "肯德基", "Kraft Foods Group": "卡夫食品",
    "Johnson and Johnson": "强生", "Discovery": "探索频道",
    "Discovery Channel": "探索频道", "Yahoo!": "雅虎",
}

# 这些本身就是拉丁字母品牌名，中文语境不翻译（强行音译反而看不懂）
KEEP_LATIN = {
    # 缩写字号 / 拉丁标识本身就是品牌
    "3M", "IBM", "SAP", "LG", "AMD", "HP", "GE", "UPS", "S&P", "EY", "BCG",
    "KPMG", "PwC", "H&M", "Nothing",
    # 中文语境通用原名，强行音译反而看不懂
    "Zara", "ZARA", "MINI", "vivo", "OPPO", "Adobe", "PayPal", "Salesforce",
    "SK On", "SK On.", "Asml", "ASML", "KLA", "Lam Research", "Tsmc",
    "Nasdaq", "NASDAQ",
    # 互联网产品通用原名
    "Instagram", "YouTube", "Zoom", "eBay", "Spotify", "MTV", "DHL",
    "LinkedIn", "Linkedin", "WhatsApp", "WeChat", "iPhone", "iPad",
}

# 中英混排需要「去掉英文尾巴」的（只保留中文部分）
STRIP_SUFFIX = {
    "谷歌Alphabet": "谷歌", "脸书Meta": "脸书", "微软Microsoft": "微软",
    "苹果Apple": "苹果", "亚马逊Amazon": "亚马逊", "英伟达NVIDIA": "英伟达",
    "中国结婚率|marriage": "中国结婚率", "原油WTI": "WTI原油",
}

# 全量合并（后面的覆盖前面的）
ALL_CN = {}
ALL_CN.update(COUNTRY_CN)
ALL_CN.update(AGG_CN)
ALL_CN.update(COMPANY_CN)
ALL_CN.update(STRIP_SUFFIX)


def _norm(s):
    """归一化：小写 + 去多余空白 + 去全角括号差异。"""
    return re.sub(r"\s+", " ", str(s)).strip().lower()


_NORM_MAP = {}
for _k, _v in ALL_CN.items():
    _NORM_MAP.setdefault(_norm(_k), _v)
# 去掉常见后缀后的兜底匹配（如 "Korea, Rep." -> "korea, rep"）
for _k, _v in ALL_CN.items():
    _NORM_MAP.setdefault(_norm(_k).rstrip("."), _v)


def cn_name(raw, default=None):
    """把任意实体名转成中文显示名。

    * 支持 "名称|代码" 格式（只转名称段，代码段原样保留）
    * 已含中文的一律原样返回（A股/ETF 的 "TCL科技"、"沪深300ETF…" 属标准写法）
    * 查不到时返回 default（默认原样）
    """
    if raw is None:
        return raw
    s = str(raw).strip()
    if not s:
        return s
    name, sep, code = s.partition("|")
    base = name.strip()
    if not base:
        return s
    # 0) 明确保留拉丁名的品牌（如 AMD / H&M / vivo），优先于字典
    if base in KEEP_LATIN or _norm(base) in {_norm(k) for k in KEEP_LATIN}:
        return base + (sep + code if sep else "")
    # 已是纯中文 -> 不动
    if re.search(r"[\u4e00-\u9fff]", base) and not re.search(r"[A-Za-z]{2,}", base):
        return base + (sep + code if sep else "")
    hit = ALL_CN.get(base) or _NORM_MAP.get(_norm(base))
    if hit:
        return hit + (sep + code if sep else "")
    return (default if default is not None else s)


def has_latin(s):
    return bool(re.search(r"[A-Za-z]", str(s or "")))


# ───────────────────────── 反查：中文 -> 英文原名 ─────────────────────────
# 存量 CSV 首列改成中文后，增量刷新脚本要把中文名还原成英文原名才能匹配上游数据源。
# 一个中文可能对应多个英文名（如 "韩国" <- "Korea, Rep." / "South Korea"），
# 故 EN_BACK 存的是「中文 -> 首选英文」；判定同一实体用 same_entity()。
EN_BACK = {}
for _k, _v in ALL_CN.items():
    EN_BACK.setdefault(_v, _k)


def en_name(cn, default=None):
    """中文名 -> 英文原名（查不到返回 default，默认原样）。"""
    if cn is None:
        return cn
    s = str(cn).strip()
    name, sep, code = s.partition("|")
    base = name.strip()
    hit = EN_BACK.get(base)
    if hit:
        return hit + (sep + code if sep else "")
    return (default if default is not None else s)


# 一个中文可能对应多个英文原名（"韩国" <- "Korea, Rep."/"South Korea"），
# 上游数据源只用其中一种，故提供候选列表供逐个尝试。
EN_CAND = {}
for _k, _v in ALL_CN.items():
    EN_CAND.setdefault(_v, []).append(_k)


def en_candidates(cn):
    """中文名 -> 可能的英文原名列表（按字典定义顺序，去重）。"""
    s = str(cn or "").strip().split("|")[0].strip()
    out = []
    for c in EN_CAND.get(s, []):
        if c not in out:
            out.append(c)
    return out


def key_of(raw):
    """统一键：把任意中英文实体名归一到同一个英文锚点，用于比对是否同一实体。"""
    s = str(raw or "").strip()
    name, _sep, code = s.partition("|")
    base = name.strip()
    if re.search(r"[\u4e00-\u9fff]", base):
        # 中文 -> 反查英文锚点；查不到就用中文自身
        base = EN_BACK.get(base, base)
    return (_norm(base), code.strip())


def same_entity(a, b):
    """两个实体名（中英不限、可带 |代码）是否指向同一实体。"""
    return key_of(a) == key_of(b)


if __name__ == "__main__":
    import sys
    for x in sys.argv[1:]:
        print("%s -> %s" % (x, cn_name(x)))
