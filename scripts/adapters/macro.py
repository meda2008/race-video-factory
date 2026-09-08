# -*- coding: utf-8 -*-
"""宏观适配器：国家统计局宏观时间序列（CPI / PPI / GDP 等）-> 泛型题材。

用 akshare 宏观接口拉取，按年取「年末值」（月度数据取 12 月，年度数据直接取），
产出单实体的逐年数值题材（mode='value'）。

params:
    indicator: 'cpi' | 'ppi' | 'gdp'   （默认 cpi）
    start_year: 起始年（默认 2010）
    title/unit/mode/decimals/highlight/legend: 展示 meta
"""
import akshare as ak

from .base import BaseAdapter

FUNC_MAP = {
    'cpi': ak.macro_china_cpi,
    'ppi': ak.macro_china_ppi,
    'gdp': ak.macro_china_gdp,
}


class MacroAdapter(BaseAdapter):
    def fetch(self, params):
        indicator = params.get('indicator', 'cpi')
        if indicator not in FUNC_MAP:
            raise SystemExit(f"ERROR: macro indicator={indicator} 不支持，可选 {list(FUNC_MAP)}")
        start_year = int(params.get('start_year', 2010))

        try:
            df = FUNC_MAP[indicator]()
        except Exception as e:
            raise SystemExit(f"ERROR: macro({indicator}) 取数失败: {e}")

        date_col = df.columns[0]
        val_col = df.columns[1]
        series = {}
        for _, r in df.iterrows():
            d = str(r[date_col])
            y = ''.join(ch for ch in d if ch.isdigit())[:4]
            if not y:
                continue
            try:
                v = float(r[val_col])
            except Exception:
                continue
            series[y] = v  # 同一年多次出现取最后一次（年末/最新）

        years = sorted(y for y in series if int(y) >= start_year)
        if not years:
            raise SystemExit(f"ERROR: macro({indicator}) 无可数据年份 >= {start_year}")

        label = {'cpi': '中国CPI', 'ppi': '中国PPI', 'gdp': '中国GDP'}.get(indicator, indicator)
        industries = [{'name': label, 'code': indicator,
                       'values': {y: round(series[y], 4) for y in years}}]

        meta = self._meta(params, default_title=f'{label}走势',
                          default_unit='', default_mode='value',
                          default_decimals=2, default_highlight=None,
                          default_legend=f'{label}逐年数值')
        src = params.get('source') or f"akshare macro_{indicator}"
        return {
            'years': years,
            'year_labels': {y: y for y in years},
            'industries': industries,
            'meta': meta,
            'source': src,
            'bg_prompt': params.get('bg_prompt'),
        }
