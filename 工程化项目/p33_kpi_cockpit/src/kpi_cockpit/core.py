# -*- coding: utf-8 -*-
"""KPI 驾驶舱：派生指标 + 等宽中文表（纯函数）。"""


def derive(k):
    produced, planned, good = float(k["produced"]), float(k["planned"]), float(k["good"])
    return {"line": str(k["line"]), "planned": int(planned), "produced": int(produced),
            "good": int(good), "oee": float(k["oee"]),
            "good_rate": round(good / produced, 4) if produced else 0.0,
            "plan_rate": round(produced / planned, 4) if planned else 0.0}


def w(s):
    """显示宽度：CJK=2，其它=1。"""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(s))


def render(rows, headers):
    """等宽文本表（中文对齐）。

    程序化发现：推导式/生成器的循环变量不得与函数后续变量同名
    （Python 闭包作用域会抛 NameError: cannot access free variable）。
    """
    cols = [list(headers)] + [[str(c) for c in row] for row in rows]
    widths = [max(w(row[i]) for row in cols) for i in range(len(headers))]

    def pad(s, n):
        s = str(s)
        return s + " " * (n - w(s))

    def line(row):
        return "  ".join(pad(row[i], widths[i]) for i in range(len(headers)))

    out = [line(cols[0]), "  ".join("-" * x for x in widths)]
    out += [line(row) for row in cols[1:]]
    return chr(10).join(out)


def table_rows(rows):
    hdr = ("产线", "计划", "产出", "合格", "合格率", "达成率", "OEE%")
    body = [(r["line"], str(r["planned"]), str(r["produced"]), str(r["good"]),
             "%.2f%%" % (r["good_rate"] * 100), "%.2f%%" % (r["plan_rate"] * 100),
             "%.1f%%" % r["oee"]) for r in rows]
    return [hdr] + body
