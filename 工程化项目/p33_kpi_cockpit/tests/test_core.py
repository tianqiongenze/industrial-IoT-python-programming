# -*- coding: utf-8 -*-
"""C 层核心函数边界测试：每个对外函数 ≥3 条边界断言（工单"≥3 boundary"）。"""
import math

import pytest

from kpi_cockpit import core


def _rules(**kw):
    """与 config.Settings.rules() 同构的阈值包（单一真源：danger=绿线、warn=黄线）。"""
    r = {"temp_max": 90.0, "vib_max": 4.5,
         "status_online": "RUN", "output_qty_per_day": 100.0, "warn": 80.0,
         "danger": 95.0, "kpi_required": [], "kpi_extra": [], "unit_symbol": "℃",
         "days": 1}
    r.update(kw)
    return r


R1 = {"ts": "2026-03-01 08:00:00", "device_id": "DEV-01", "line": "一号产线",
      "output": 60, "ok_qty": 57, "yield_pct": 95.0, "temp": 70.0, "vib": 3.0,
      "status": "RUN"}
R2 = {"ts": "2026-03-02 08:00:00", "device_id": "DEV-02", "line": "二号产线",
      "output": 40, "ok_qty": 30, "yield_pct": 75.0, "temp": 91.0, "vib": 5.0,
      "status": "DOWN"}


# ------------------------------------------------------------------ derive（3 边界）
def test_derive_normal():
    r = core.derive({"line": "A", "planned": 100, "produced": 80, "good": 70, "oee": 50.0})
    assert r["good_rate"] == 0.875 and r["plan_rate"] == 0.8


@pytest.mark.parametrize("planned,produced,good", [(0, 0, 0), (100, 0, 0), (0, 50, 50)])
def test_derive_zero_division_safe(planned, produced, good):
    r = core.derive({"line": "A", "planned": planned, "produced": produced,
                     "good": good, "oee": 0})
    assert r["good_rate"] in (0.0, 1.0) and r["plan_rate"] in (0.0, math.inf)


def test_derive_coerces_str_numbers():
    r = core.derive({"line": "A", "planned": "100", "produced": "50", "good": "45",
                     "oee": "12.5"})
    assert r["good_rate"] == 0.9 and r["planned"] == 100 and r["oee"] == 12.5


def test_derive_good_gt_produced_is_not_clamped():
    """边界：合格 > 产出（脏数据）—— 良率会 >1，由上层断言拦截，不静默改数。"""
    r = core.derive({"line": "A", "planned": 10, "produced": 5, "good": 8, "oee": 1})
    assert r["good_rate"] == 1.6


# ------------------------------------------------------------- 表格与宽度（3 边界）
def test_width_cjk_is_two():
    assert core.w("产线") == 4 and core.w("A1") == 2


@pytest.mark.parametrize("txt", ["", "ＡＢ", "混合mix"])
def test_width_edge_cases(txt):
    assert core.w(txt) >= 0


def test_render_alignment_by_display_width():
    rows = [("一号产线", "960"), ("B", "10")]
    out = core.render(rows, ("产线", "计划")).splitlines()
    assert len({core.w(ln) for ln in out}) == 1


def test_render_first_cell_padded_to_width():
    out = core.render([("一号产线", "960")], ("产线", "计划")).splitlines()[2]
    assert core.w(out.split("  ")[0]) == 8


def test_render_empty_rows_still_has_header():
    out = core.render([], ("a",)).splitlines()
    assert len(out) == 2


def test_table_rows_shape():
    rows = [core.derive({"line": "A", "planned": 10, "produced": 9, "good": 8, "oee": 50.0})]
    tbl = core.table_rows(rows)
    assert len(tbl) == 2 and len(tbl[0]) == 7


# ------------------------------------------------------- filter_records（5 条边界）
def test_filter_by_date_range_inclusive():
    got = core.filter_records([R1, R2], start="2026-03-01", end="2026-03-01")
    assert [r["device_id"] for r in got] == ["DEV-01"]


def test_filter_by_device_multiselect():
    got = core.filter_records([R1, R2], devices=["DEV-02"])
    assert len(got) == 1 and got[0]["status"] == "DOWN"


def test_filter_single_date_wins_over_range():
    assert len(core.filter_records([R1, R2], start="2026-03-01", end="2026-03-02",
                                   date="2026-03-02")) == 1


@pytest.mark.parametrize("kw,exp", [
    ({}, 2),                                    # 边界1：不加条件 → 原样
    ({"start": "2030-01-01"}, 0),               # 边界2：未来区间 → 空
    ({"devices": ["NOPE"]}, 0),                 # 边界3：不存在的设备 → 空
    ({"devices": []}, 2),                       # 边界4：空选择 = 不过滤
])
def test_filter_boundaries(kw, exp):
    assert len(core.filter_records([R1, R2], **kw)) == exp


def test_filter_drops_row_without_ts():
    bad = {"ts": "", "device_id": "X", "output": 1}
    assert core.filter_records([bad, R1]) == [R1]


def test_previous_window_shifts_by_days():
    got = core.previous_window([R1, R2], "2026-03-02", "2026-03-02", 1)
    assert [r["device_id"] for r in got] == ["DEV-01"]


def test_previous_window_empty_when_no_range():
    assert core.previous_window([R1], None, None, 1) == []


# --------------------------------------------------------------- 单指标（各 ≥3 边界）
@pytest.mark.parametrize("recs,exp", [([], 0), ([{"output": 0}], 0),
                                      ([{"output": 3}, {"output": "4"}], 7)])
def test_total_output_boundaries(recs, exp):
    assert core.total_output(recs) == exp


@pytest.mark.parametrize("recs,exp", [([], 0.0), ([{"output": 10, "ok_qty": 9}], 90.0),
                                      ([{"output": 0, "ok_qty": 0}], 0.0)])
def test_avg_yield_boundaries(recs, exp):
    assert core.avg_yield_pct(recs) == exp


@pytest.mark.parametrize("vib,exp", [(4.5, 0), (4.51, 1), (float("nan"), 0)])
def test_alarm_rows_is_strictly_greater(vib, exp):
    r = dict(R1, vib=vib)
    assert len(core.alarm_rows([r], 4.5)) == exp


def test_online_devices_uses_last_record_per_device():
    recs = [{"device_id": "A", "status": "RUN", "ts": "2026-03-01 01:00:00"},
            {"device_id": "A", "status": "DOWN", "ts": "2026-03-01 02:00:00"},
            {"device_id": "B", "status": "RUN", "ts": "2026-03-01 03:00:00"}]
    assert core.online_devices(recs, "RUN") == (1, 2)


@pytest.mark.parametrize("recs,exp", [([], (0, 0)), ([{"device_id": "A", "status": "X"}], (0, 1))])
def test_online_devices_boundaries(recs, exp):
    assert core.online_devices(recs, "RUN") == exp


@pytest.mark.parametrize("tot,tgt,days,clip,raw", [
    (0, 100, 1, 0.0, 0.0),                      # 边界1：零产量
    (100, 100, 1, 1.0, 1.0),                    # 边界2：正好达标
    (150, 100, 1, 1.0, 1.5),                    # 边界3：超额被截断到 1.0
    (200, 100, 2, 1.0, 1.0),                    # 边界4：跨 2 天目标折算
])
def test_efficiency_boundaries(tot, tgt, days, clip, raw):
    recs = [{"output": tot}]
    c, r = core.efficiency(recs, tgt, days)
    assert (c, r) == (clip, raw)


def test_efficiency_rejects_non_positive_target():
    with pytest.raises(ValueError):
        core.efficiency([{"output": 1}], 0, 1)


@pytest.mark.parametrize("recs,exp", [([], 0.0), ([{"temp": 10}, {"temp": 20}], 15.0),
                                     ([{"temp": "x"}], 0.0)])
def test_mean_temp_boundaries(recs, exp):
    assert core.mean_temp(recs) == exp


def test_max_vib_empty_is_zero():
    assert core.max_vib([]) == 0.0


@pytest.mark.parametrize("lines,exp", [(None, None), ([], None),
                                       ([{"oee": 80}, {"oee": 90}], 85.0)])
def test_oee_mean_boundaries(lines, exp):
    assert core.oee_mean(lines) == exp


def test_plan_rate_zero_planned():
    assert core.plan_rate([{"produced": 5, "planned": 0}]) == 0.0


# ----------------------------------------------------------------- compute_kpis
def test_compute_kpis_returns_required_five_in_order():
    rules = _rules(kpi_required=["总产量", "平均良率", "设备在线数", "今日告警数", "效率对标"])
    got = [k["name"] for k in core.compute_kpis([R1, R2], rules)]
    assert got == ["总产量", "平均良率", "设备在线数", "今日告警数", "效率对标"]


def test_compute_kpis_five_are_all_populated():
    kpis = core.kpi_map(core.compute_kpis([R1, R2], _rules()))
    for n in ("总产量", "平均良率", "设备在线数", "今日告警数", "效率对标"):
        assert kpis[n]["value"] is not None and kpis[n]["text"]


def test_compute_kpis_alarm_tone_is_error_when_any():
    kpis = core.kpi_map(core.compute_kpis([dict(R1, vib=5.0)], _rules()))
    assert kpis["今日告警数"]["tone"] == "error"


def test_compute_kpis_rejects_unknown_kpi_name():
    with pytest.raises(ValueError, match="未实现指标"):
        core.compute_kpis([R1], _rules(kpi_required=["不存在的指标"]))


def test_compute_kpis_empty_records_no_crash():
    assert core.compute_kpis([], _rules())


def test_compute_kpis_delta_requires_prev_window():
    rules = _rules(kpi_required=["总产量"])
    cur = core.compute_kpis([dict(R1, output=100)], rules)
    prev = core.compute_kpis([dict(R1, output=80)], rules)
    assert cur[0]["delta"] == ""                       # 无上一窗 → 不谎报涨跌
    k2 = core.compute_kpis([dict(R1, output=100)], rules, prev=[dict(R1, output=80)])
    assert k2[0]["delta"] == "+20.00"


def test_compute_kpis_online_total_and_tone():
    rules = _rules(kpi_required=["设备在线数"])
    got = core.compute_kpis([{"device_id": "A", "status": "RUN"},
                             {"device_id": "B", "status": "DOWN"}], rules)[0]
    assert got["text"] == "1/2" and got["total"] == 2 and got["tone"] == "warn"


# ------------------------------------------------------- gauge / 灯态 / 趋势 / 附表
def test_gauge_delta_against_target():
    g = core.gauge([{"output": 100, "ok_qty": 90}], _rules())
    assert g["value"] == 90.0 and g["delta"] == -5.0 and g["tone"] == "warn"


def test_gauge_tone_follows_config_lines_not_hardcoded():
    """同一条数据，只改 config 阈值（danger/warn）就应换灯色——证明阈值真由配置驱动。"""
    recs = [{"output": 100, "ok_qty": 88}]
    assert core.gauge(recs, _rules())["tone"] == "warn"          # 80 ≤ 88 < 95
    assert core.gauge(recs, _rules(danger=85.0))["tone"] == "ok"  # 88 ≥ 85 → 绿
    assert core.gauge(recs, _rules(warn=90.0))["tone"] == "error"  # 88 < 90 → 红


def test_gauge_all_good_is_ok():
    assert core.gauge([{"output": 1, "ok_qty": 1}], _rules())["tone"] == "ok"


def test_gauge_empty_records():
    g = core.gauge([], _rules())
    assert g["value"] == 0.0 and g["delta"] == -95.0 and g["tone"] == "error"


def test_device_status_three_levels():
    recs = [{"device_id": "A", "status": "RUN", "vib": 1.0, "temp": 50.0},
            {"device_id": "B", "status": "RUN", "vib": 5.0, "temp": 50.0},
            {"device_id": "C", "status": "DOWN", "vib": 1.0, "temp": 50.0}]
    st = {d["device_id"]: d["tone"] for d in core.device_status(recs, _rules())}
    assert st == {"A": "ok", "B": "warn", "C": "error"}


def test_device_status_empty():
    assert core.device_status([], _rules()) == []


def test_device_status_sorted_and_labeled():
    got = core.device_status([dict(R2), dict(R1, device_id="A0")], _rules())
    assert [d["device_id"] for d in got] == ["A0", "DEV-02"]
    assert got[1]["light"] == core.STATUS_TONE[got[1]["tone"]]


@pytest.mark.parametrize("bucket", ["hour", "day"])
def test_trend_buckets(bucket):
    pts = core.trend([R1, R2], bucket=bucket)
    assert len(pts) == (2 if bucket == "hour" else 2)
    assert all("output" in p and "ts" in p for p in pts)


def test_trend_aggregates_same_key():
    pts = core.trend([dict(R1), dict(R1)], bucket="day")
    assert len(pts) == 1 and pts[0]["output"] == 120 and pts[0]["n"] == 2


def test_trend_empty():
    assert core.trend([], bucket="day") == []


@pytest.mark.parametrize("n,exp", [(0, 0), (1, 1), (99, 2)])
def test_tail_rows_boundaries(n, exp):
    assert len(core.tail_rows([R1, R2], n)) == exp


# ------------------------------------------------------------ 异常识别与处置建议
def test_anomalies_hits_temp_rule():
    a = core.anomalies([dict(R1, temp=95.0)], _rules(), topk=None)
    assert len(a) == 1 and "temp" in a[0]["reasons"] and "冷却风机" in a[0]["suggestion"]


def test_anomalies_hits_vib_rule_only():
    a = core.anomalies([dict(R1, vib=4.6, temp=50.0)], _rules(), topk=None)
    assert a[0]["reasons"] == "vib" and "动平衡" in a[0]["suggestion"]


def test_anomalies_both_rules():
    a = core.anomalies([dict(R1, vib=6.0, temp=99.0)], _rules(), topk=None)
    assert set(a[0]["reasons"].split(",")) == {"temp", "vib"}


@pytest.mark.parametrize("temp,vib,exp", [(90.0, 4.5, 0), (90.01, 0.0, 1),
                                          (0.0, 4.51, 1), (20.0, 1.0, 0)])
def test_anomalies_threshold_is_strict(temp, vib, exp):
    assert len(core.anomalies([dict(R1, temp=temp, vib=vib)], _rules(), topk=None)) == exp


def test_anomalies_topk_truncates_and_sorts_by_severity():
    recs = [dict(R1, device_id="A", vib=4.6), dict(R1, device_id="B", vib=6.0)]
    a = core.anomalies(recs, _rules(), topk=1)
    assert len(a) == 1 and a[0]["device_id"] == "B"


def test_anomalies_ignores_non_numeric():
    assert core.anomalies([dict(R1, temp="N/A", vib="N/A")], _rules(), topk=None) == []


def test_suggest_offline_device_message():
    hits = core.suggest(dict(R1, status="IDLE"), _rules())
    assert hits and hits[0][0] == "offline"


def test_suggest_clean_row_returns_empty():
    assert core.suggest(R1, _rules()) == []


# ------------------------------------------------------------------------- 钻取
def test_drill_scopes_to_one_device():
    d = core.drill([R1, R2, dict(R1, device_id="DEV-01", vib=6.0)], "DEV-01", _rules())
    assert d["n"] == 2 and d["alarms"] == 1 and d["max_vib"] == 6.0


def test_drill_unknown_device_is_empty_not_error():
    d = core.drill([R1], "NOPE", _rules())
    assert d["n"] == 0 and d["yield_pct"] == 0.0 and d["top_anomalies"] == []


def test_drill_topk_limits_anomaly_list():
    recs = [dict(R1, vib=5.0 + i / 10) for i in range(5)]
    assert len(core.drill(recs, "DEV-01", _rules(), topk=2)["top_anomalies"]) == 2


def test_tone_boundaries_are_config_driven_and_inclusive():
    r = _rules()  # warn=80 / danger=95
    assert core.tone(96, r) == "ok"
    assert core.tone(95, r) == "ok"      # 边界：等于绿线 → 绿（达标即绿灯）
    assert core.tone(94.99, r) == "warn"
    assert core.tone(80, r) == "warn"    # 边界：等于黄线 → 黄
    assert core.tone(79.99, r) == "error"
    assert core.tone(0, r) == "error"


def test_status_tone_mapping_covers_three():
    assert set(core.STATUS_TONE) == {"ok", "warn", "error"}
    assert core.STATUS_TONE["ok"] == "绿灯"


# ----------------------------------------------------------- A 层 drill_rows
# 工单 A 层"点击折线点弹出该时段明细表"：app.py 选择事件与 CLI 证据行共用这一份逻辑。
def _det_rows():
    return [dict(R1), dict(R1, ts="2026-03-01 12:00:00", device_id="DEV-02"),
            dict(R1, ts="2026-03-02 08:00:00", vib=5.0),
            dict(R1, ts="2026-03-02 12:00:00", device_id="DEV-02"),
            dict(R2, ts="2026-03-02 16:00:00")]


def test_drill_rows_normal_point_click_hits_time_bucket():
    det = core.drill_rows([{"x": "2026-03-01"}], _det_rows(), _rules())
    assert [r["ts"] for r in det] == ["2026-03-01 08:00:00", "2026-03-01 12:00:00"]


def test_drill_rows_exact_hour_bucket_and_device_combo():
    rows = _det_rows()
    det = core.drill_rows([{"x": "2026-03-02 08:00:00"}], rows, _rules())
    assert len(det) == 1
    det = core.drill_rows([{"x": "2026-03-02", "device_id": "DEV-02"}], rows, _rules())
    assert [r["ts"] for r in det] == ["2026-03-02 12:00:00", "2026-03-02 16:00:00"]


def test_drill_rows_empty_selection_returns_empty():
    rows = _det_rows()
    assert core.drill_rows([], rows, _rules()) == []
    assert core.drill_rows(None, rows, _rules()) == []


def test_drill_rows_malformed_or_out_of_range_points_ignored():
    rows = _det_rows()
    junk = ["不是dict", {}, {"x": ""}, {"x": None}, {"row": 999}, {"row": -3},
            {"row": True}, {"row": "abc"}, {"x": "2099-01-01"}]
    assert core.drill_rows(junk, rows, _rules()) == []   # 防御：绝不抛异常、绝不全表命中


def test_drill_rows_table_row_selection_expands_to_device_day():
    rows = _det_rows()
    det = core.drill_rows([{"row": 0}], rows, _rules())    # DEV-01 的 2026-03-01 行
    assert all(str(r["ts"]).startswith("2026-03-01") and r["device_id"] == "DEV-01"
               for r in det)
    assert len(det) == 1
    det = core.drill_rows([2], rows, _rules())             # 裸整数 = 行号选择
    assert [r["ts"] for r in det] == ["2026-03-02 08:00:00"]


def test_drill_rows_dedupes_and_keeps_rows_order_regardless_of_point_order():
    rows = _det_rows()
    a = core.drill_rows([{"x": "2026-03-02"}, {"x": "2026-03-01"}, {"x": "2026-03-02"}],
                        rows, _rules())
    b = core.drill_rows([{"x": "2026-03-01"}, {"x": "2026-03-02"}], rows, _rules())
    assert a == b and len(a) == 5                          # 原时序输出、重复点去重


def test_drill_rows_max_rows_and_columns_come_from_rules():
    rows = _det_rows()
    capped = core.drill_rows([{"x": "2026-03-02"}], rows, _rules(drill_max_rows=2))
    assert len(capped) == 2
    assert core.drill_rows([{"x": "2026-03-01"}], rows, _rules(drill_max_rows=0)) == []
    proj = core.drill_rows([{"x": "2026-03-01"}], rows,
                           _rules(drill_detail_columns=["ts", "vib"]))
    assert all(set(r) == {"ts", "vib"} for r in proj)


def test_drill_fingerprint_is_crc32_not_builtin_hash():
    """确定性：指纹必须等于 zlib.crc32 规范序列化（builtin hash() 受 PYTHONHASHSEED 随机化，
    不能当证据）。同内容换 dict 键插入顺序，指纹不变。"""
    import json
    import zlib
    rows_a = _det_rows()
    rows_b = [{k: r[k] for k in sorted(r)} for r in rows_a]  # 键插入顺序不同、内容相同
    det = core.drill_rows([{"x": "2026-03-01"}], rows_a, _rules())
    det2 = core.drill_rows([{"x": "2026-03-01"}], rows_b, _rules())
    assert core.drill_fingerprint(det) == core.drill_fingerprint(det2)
    canon = json.dumps([[[k, str(v)] for k, v in sorted(r.items())] for r in det],
                       ensure_ascii=False, separators=(",", ":"))
    assert core.drill_fingerprint(det) == "%08x" % zlib.crc32(canon.encode("utf-8"))
    assert core.drill_fingerprint([]) == "%08x" % zlib.crc32(b"[]")
