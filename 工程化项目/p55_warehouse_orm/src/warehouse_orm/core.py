# -*- coding: utf-8 -*-
"""极简 ORM：内存表 + 倒排索引 + 查询计划（零依赖，原理可见）。"""


class Table:
    """内存表：字段约束 + 行存储 + 倒排索引。"""

    def __init__(self, name, fields):
        if not fields:
            raise ValueError("表 %s 未定义字段" % name)
        self.name = name
        self.fields = list(fields)
        self.rows = []
        self.indexes = {}          # col -> {value: set(row_idx)}

    def insert(self, rec):
        missing = [f for f in self.fields if f not in rec]
        if missing:
            raise ValueError("缺少字段: %s" % missing)
        idx = len(self.rows)
        self.rows.append(dict(rec))
        for col, inv in self.indexes.items():
            inv.setdefault(rec[col], set()).add(idx)
        return idx

    def create_index(self, col):
        if col not in self.fields:
            raise ValueError("字段不存在: %s" % col)
        inv = {}
        for i, r in enumerate(self.rows):
            inv.setdefault(r[col], set()).add(i)
        self.indexes[col] = inv
        return col

    def where(self, **kw):
        """等值查询：有索引走索引，否则全表扫描。"""
        if len(kw) == 1:
            (col, val), = kw.items()
            if col in self.indexes:
                return [self.rows[i] for i in sorted(self.indexes[col].get(val, set()))]
        return [r for r in self.rows
                if all(r.get(k) == v for k, v in kw.items())]

    def explain(self, **kw):
        if len(kw) == 1:
            (col, _), = kw.items()
            if col in self.indexes:
                return "INDEX SCAN on %s" % col
        return "FULL SCAN on %s" % self.name
