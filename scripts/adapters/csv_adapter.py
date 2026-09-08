# -*- coding: utf-8 -*-
"""CSV 适配器：任意「实体 × 年份 × 数值」宽表 -> 泛型题材。

CSV 格式（首行表头，首列实体名）：
    name,2015,2016,2017
    食品饮料|801120,10.2,25.6,30.1
    家用电器,8.1,19.3,22.0
- 首列可用 '名称|代码' 形式附带 code；不带 code 则留空。
- params:
    path: CSV 路径（相对 workspace 或绝对）
    value_multiplier: 数值统一乘的系数（如 百分点 -> %）
    title/unit/mode/decimals/highlight/legend/source/bg_prompt: 展示与来源
"""
import csv
import os

from .base import BaseAdapter


class CSVAdapter(BaseAdapter):
    def fetch(self, params):
        ws = params.get('_ws')
        script_dir = params.get('_script_dir')
        path = params['path']
        if not os.path.isabs(path):
            cand = path
            if ws:
                cand = os.path.join(ws, path)
            if not os.path.exists(cand) and script_dir:
                cand2 = os.path.join(script_dir, path)
                if os.path.exists(cand2):
                    cand = cand2
            path = cand
        if not os.path.exists(path):
            raise SystemExit(f"ERROR: CSV 不存在 {path}")

        mult = float(params.get('value_multiplier', 1.0))
        years = []
        industries = []
        with open(path, encoding='utf-8-sig', newline='') as f:
            r = csv.reader(f)
            header = next(r)
            years = [h.strip() for h in header[1:]]
            for row in r:
                if not row or not row[0].strip():
                    continue
                cell = row[0].strip()
                if '|' in cell:
                    name, code = cell.split('|', 1)
                    name, code = name.strip(), code.strip()
                else:
                    name, code = cell, ''
                vals = {}
                for i, y in enumerate(years):
                    raw = row[i + 1].strip() if i + 1 < len(row) else ''
                    vals[y] = (float(raw) * mult) if raw not in ('', None) else 0.0
                industries.append({'name': name, 'code': code, 'values': vals})

        if not industries:
            raise SystemExit("ERROR: CSV 无数据行")

        meta = self._meta(params, default_title=os.path.basename(path),
                          default_unit='', default_mode='value', default_decimals=2)
        src = params.get('source') or f"CSV: {os.path.basename(path)}"
        return {
            'years': years,
            'year_labels': {y: y for y in years},
            'industries': industries,
            'meta': meta,
            'source': src,
            'bg_prompt': params.get('bg_prompt'),
        }
