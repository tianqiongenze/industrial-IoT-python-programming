# -*- coding: utf-8 -*-

from kpi_cockpit import core


def test_derive_rates():
    r = core.derive({"line": "A", "planned": 100, "produced": 80, "good": 70, "oee": 50.0})
    assert r["good_rate"] == 0.875 and r["plan_rate"] == 0.8


def test_derive_zero_division_safe():
    r = core.derive({"line": "A", "planned": 0, "produced": 0, "good": 0, "oee": 0})
    assert r["good_rate"] == 0.0 and r["plan_rate"] == 0.0


def test_width_cjk_is_two():
    assert core.w("产线") == 4 and core.w("A1") == 2


def test_render_alignment_by_display_width():
    """对齐按'显示宽度'（CJK=2）而非字符数——这是中文表格的正确口径。"""
    rows = [("一号产线", "960"), ("B", "10")]
    out = core.render(rows, ("产线", "计划")).splitlines()
    assert len({core.w(ln) for ln in out}) == 1


def test_render_first_cell_padded_to_width():
    rows = [("一号产线", "960")]
    out = core.render(rows, ("产线", "计划")).splitlines()[2]
    assert core.w(out.split("  ")[0]) == 8


def test_table_rows_shape():
    rows = [core.derive({"line": "A", "planned": 10, "produced": 9, "good": 8, "oee": 50.0})]
    tbl = core.table_rows(rows)
    assert len(tbl) == 2 and len(tbl[0]) == 7
