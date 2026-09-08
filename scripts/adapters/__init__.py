# -*- coding: utf-8 -*-
"""可扩展数据源适配器注册表。

每个适配器把一种数据源归一化为 build_race 的「泛型题材契约」(与 run.normalize_topic
的 else 分支对齐)，从而让题材数量从「手写死的 5 个 JSON」变成「配置即榜单」。

泛型 raw dict 结构：
{
  "years": ["2015", "2016", ...],
  "year_labels": {"2015": "2015", ...},      # 可选
  "industries": [
     {"name": "食品饮料", "code": "801120", "values": {"2015": 112.3, ...}}
  ],
  "meta": {"title","subtitle","unit","mode","decimals","highlight","legend"},
  "source": "文本",            # 可选，写进文案来源
  "bg_prompt": "文本"         # 可选，覆盖默认背景提示
}
"""
from .base import BaseAdapter
from .csv_adapter import CSVAdapter
from .akshare_ashare import AShareAdapter
from .macro import MacroAdapter

ADAPTERS = {
    'csv': CSVAdapter,
    'ashare': AShareAdapter,
    'macro': MacroAdapter,
}


def get_adapter(name):
    if name not in ADAPTERS:
        raise SystemExit(f"ERROR: 未知数据源适配器 {name!r}，可选 {list(ADAPTERS)}")
    return ADAPTERS[name]()


def list_adapters():
    return list(ADAPTERS.keys())
