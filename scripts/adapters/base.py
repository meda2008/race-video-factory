# -*- coding: utf-8 -*-
"""数据适配器基类。"""
from abc import ABC, abstractmethod


class BaseAdapter(ABC):
    @abstractmethod
    def fetch(self, params: dict) -> dict:
        """子类实现：返回泛型 raw dict（见包文档）。"""
        raise NotImplementedError

    # 从 params / params['meta'] 取展示 meta，缺省给通用值。
    # params 顶层与 params['meta'] 都认，方便 YAML 里直接写。
    def _meta(self, params, default_title='未命名题材', default_unit='',
              default_mode='value', default_decimals=2, default_highlight=None,
              default_legend=''):
        p = params or {}
        m = (p.get('meta') if isinstance(p.get('meta'), dict) else {}) or {}
        title = m.get('title') or p.get('title') or default_title
        subtitle = m.get('subtitle') or p.get('subtitle') or ''
        unit = m.get('unit', p.get('unit', default_unit))
        mode = m.get('mode', p.get('mode', default_mode))
        decimals = int(m.get('decimals', p.get('decimals', default_decimals)))
        highlight = m.get('highlight', p.get('highlight', default_highlight))
        legend = m.get('legend', p.get('legend', default_legend))
        return {
            'title': title, 'subtitle': subtitle, 'unit': unit,
            'mode': mode, 'decimals': decimals,
            'highlight': highlight, 'legend': legend,
        }
