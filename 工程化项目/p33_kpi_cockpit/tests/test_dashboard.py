# -*- coding: utf-8 -*-
"""TODO-1~TODO-5 的"真仪表盘"验证：用 streamlit.testing.v1.AppTest 无头执行 app.py。

审计项修复：以前只有 core 测试，app.py 是否存在、能否跑起来无人证明。
这里不启浏览器、不联网，直接执行同一份 app.py 并断言控件与联动结果。
"""
import os

import pytest

from kpi_cockpit import deps

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(HERE, "app.py")

pytestmark = pytest.mark.skipif(
    not deps.probe("streamlit").installed,
    reason="streamlit 未安装：headless 兜底路径由 run.py + tests/test_pipeline.py 覆盖")


@pytest.fixture(scope="module")
def at():
    from streamlit.testing.v1 import AppTest
    inst = AppTest.from_file(APP, default_timeout=120).run()
    assert not inst.exception, "app.py 首屏即抛异常：%s" % [e.value for e in inst.exception]
    return inst


def test_app_file_exists_and_is_a_real_streamlit_app():
    text = open(APP, encoding="utf-8").read()
    for token in ("st.sidebar.date_input", "st.sidebar.multiselect", "px.line",
                  "st.plotly_chart", ".metric(", "st.progress", "st.cache_data",
                  "go.Indicator", "st.columns(4)"):
        assert token in text, "TODO 要求的 %s 不在 app.py 里" % token


def test_alarm_card_marks_rising_as_bad():
    """工单避坑：告警数"越高越坏"，delta 颜色必须 inverse（AppTest 不回传该字段，查源码）。"""
    text = open(APP, encoding="utf-8").read()
    i = text.index('c4.metric("今日告警数"')
    assert 'delta_color="inverse"' in text[i:i + 260]


# ------------------------------------------------------------------ TODO-1 侧栏筛选
def test_sidebar_has_date_and_multiselect_controls(at):
    assert len(at.sidebar.date_input) >= 1, "TODO-1 日期控件缺失"
    assert len(at.sidebar.multiselect) >= 1, "TODO-1 设备多选缺失"
    picked = [m.value for m in at.sidebar.multiselect]
    assert any(isinstance(v, list) and v for v in picked), "多选默认应全选，首屏非空"


def test_unselecting_all_devices_falls_back_with_warning(at):
    """边界：设备全不选 → 显式提示并回退，不给出一张空仪表盘。"""
    from streamlit.testing.v1 import AppTest
    inst = AppTest.from_file(APP, default_timeout=120).run()
    inst.sidebar.multiselect[0].set_value([]).run()
    assert not inst.exception
    assert any("未选设备" in w.value for w in inst.warning)
    assert len(inst.metric) >= 4, "回退后指标卡仍在"


def test_single_day_mode_narrows_hit_rows(at):
    """联动：切到"单日"后，caption 的命中行数必须变小（证明筛选真的接进了计算）。"""
    import re
    from streamlit.testing.v1 import AppTest
    base = AppTest.from_file(APP, default_timeout=120).run()
    cap_all = " ".join(c.value for c in base.caption)
    m = re.search(r"命中 (\d+) 行", cap_all)
    assert m, "caption 未报告命中行数：%s" % cap_all[:120]
    total = int(m.group(1))
    inst = AppTest.from_file(APP, default_timeout=120).run()
    inst.sidebar.radio[0].set_value("单日")
    inst.run()
    assert not inst.exception
    one = int(re.search(r"命中 (\d+) 行", " ".join(c.value for c in inst.caption)
                        ).group(1))
    assert one < total, "单日命中应少于全量：%d vs %d" % (one, total)


# ------------------------------------------------------------------ TODO-2 指标卡
def test_four_required_metric_cards(at):
    names = [m.label for m in at.metric]
    for need in ("总产量", "平均良率", "设备在线数", "今日告警数"):
        assert need in names, "TODO-2 指标卡缺失：%s" % need
    assert len(at.metric) >= 7, "工单要求 ≥7 指标（B 层佐证），实得 %d" % len(at.metric)


def test_metric_values_are_rendered_not_placeholder(at):
    for m in at.metric:
        assert m.value and m.value not in ("-", "nan", "None")


# ------------------------------------------------------------------ TODO-3/4 图表
def test_plotly_charts_present(at):
    charts = at.get("plotly_chart")
    assert len(charts) >= 2, "趋势图 + 良率仪表至少两张（TODO-3/TODO-4）"


def test_traffic_lights_render_three_states(at):
    """TODO-4 红绿灯：合成数据里必然同时有绿/黄/红三种提示。"""
    assert len(at.success) + len(at.warning) + len(at.error) >= 3
    assert len(at.error) >= 1, "存在 DOWN/超温设备却无红灯 → 定级逻辑失效"


def test_alarm_and_anomaly_tables(at):
    assert len(at.dataframe) >= 2, "告警表 + 异常表（TODO-4）"


# ------------------------------------------------------------------ TODO-5 进度条
def test_progress_bar_exists_and_bounded(at):
    prog = at.get("progress")
    assert len(prog) >= 1, "TODO-5 效率对标进度条缺失"
    # AppTest 回传的是 0~100 的百分比整数（st.progress 内部换算），不得溢出
    assert 0 <= float(prog[0].value) <= 100, "进度值越界 → st.progress(>1) 会抛错"


def test_progress_text_carries_target_and_actual(at):
    text = at.get("progress")[0].text or ""
    assert "效率对标" in text and "目标" in text and "实际" in text


# ------------------------------------------------------------------ 缓存/来源诚实
def test_cache_decorator_declared_with_ttl():
    text = open(APP, encoding="utf-8").read()
    assert "@st.cache_data(ttl=CFG.cache_ttl" in text, "工程化要求 2：缓存必须带 TTL"


def test_source_line_honest_about_provenance(at):
    cap = " ".join(c.value for c in at.caption)
    assert "数据源：" in cap and ("seed=" in cap or "sha256=" in cap), \
        "首屏必须写清用了哪个数据源（TODO-0 审计口径）"


# ------------------------------------------------- A 层：选择事件联动明细（工单 A）
def test_drill_down_on_select_wired_in_app_source():
    """A 层闸门：联动必须真接在 on_select 选择事件上（AppTest 无法伪造前端点击，
    所以接线查源码；行为在 tests/test_core.py 与 test_tier_gates.py 逐条复算）。"""
    text = open(APP, encoding="utf-8").read()
    assert text.count('on_select="rerun"') >= 2, "趋势图与告警表都必须接 on_select"
    assert 'st.plotly_chart(fig_line' in text and 'key="trend_drill"' in text, \
        "趋势图须以 on_select=rerun + 稳定 key 注册选择事件"
    assert 'key="alarm_table"' in text and "selection_mode=" in text, \
        "告警表须以 st.dataframe(on_select=rerun) 行选择联动"
    assert "core.drill_rows" in text, "过滤逻辑必须走 core.drill_rows（禁止 app 内私设一套）"


def test_drill_panel_renders_with_selection_hint(at):
    """无选择事件的首屏：联动明细面板必须渲染并指导"点击折线点/告警行"，
    而不是旧的 selectbox 假钻取（工单 A 层审计项）。"""
    caps = " ".join(c.value for c in at.caption)
    assert "折线点" in caps and "on_select" in caps, "首屏应明示选择口径"
    assert len(at.dataframe) >= 3, "告警表 + 异常表 + 联动明细面板都在"
    text = open(APP, encoding="utf-8").read()
    assert "st.selectbox(\"钻取设备\"" not in text, "旧的 selectbox 假联动必须移除"
