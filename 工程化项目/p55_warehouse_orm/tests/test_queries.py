# -*- coding: utf-8 -*-
"""种子/统计查询/窗口环比/溯源/复杂聚合测试（C层步骤2-3 + A层；starter任务卡 T3/T4）。"""
import datetime as dt
import os

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from warehouse_orm import core
from warehouse_orm.models import AlarmEvent, Device, Record, SensorPoint


@pytest.fixture(scope="module")
def seeded_engine(tmp_path_factory):
    eng = core.make_engine("sqlite:///%s" % (tmp_path_factory.mktemp("p5q") / "wh.db"))
    core.init_db(eng)
    core.seed_demo(eng, seed=7, n_records=500, warn=4.5, danger=6.0)
    return eng


def test_seed_counts(seeded_engine):
    with Session(seeded_engine) as s:
        assert s.query(Device).count() == 3
        assert s.query(SensorPoint).count() == 6
        assert s.query(Record).count() == 500
        assert s.query(AlarmEvent).count() > 0          # 约5% vib 越线
        # 告警级别口径：level 全为 1/2，且 message 含越线值
        levels = {a.level for a in s.query(AlarmEvent)}
        assert levels <= {1, 2} and levels != set()


def test_seed_deterministic(tmp_path):
    e1 = core.make_engine("sqlite:///%s/a.db" % tmp_path)
    e2 = core.make_engine("sqlite:///%s/b.db" % tmp_path)
    core.init_db(e1)
    core.init_db(e2)
    core.seed_demo(e1, seed=7, n_records=300)
    core.seed_demo(e2, seed=7, n_records=300)
    with Session(e1) as s1, Session(e2) as s2:
        assert core.avg_vib_per_device(s1) == core.avg_vib_per_device(s2)


def test_avg_vib_matches_manual_join(seeded_engine):
    """查询正确性：ORM 聚合 vs 手动逐行平均，两路相互印证。"""
    with Session(seeded_engine) as s:
        rows = dict((r[0], r[1]) for r in core.avg_vib_per_device(s))
        manual = {}
        for d in s.query(Device):
            vals = [r.value for r in s.query(Record)
                    .join(SensorPoint, Record.point_id == SensorPoint.id)
                    .filter(SensorPoint.device_id == d.id,
                            SensorPoint.metric == "vib")]
            manual[d.code] = round(sum(vals) / len(vals), 4)
        assert set(rows) == {"DEV-01", "DEV-02", "DEV-03"}
        for code in rows:
            assert abs(rows[code] - manual[code]) < 1e-6


def test_alarm_top3_sorted_and_capped(seeded_engine):
    with Session(seeded_engine) as s:
        top = core.alarm_top_devices(s, topk=3)
        assert 1 <= len(top) <= 3
        counts = [r[2] for r in top]
        assert counts == sorted(counts, reverse=True)
        # 与直接计数一致
        total = s.query(AlarmEvent).count()
        assert sum(counts) <= total
        assert all(isinstance(r[1], str) for r in top)     # area 字段随行返回


def test_hourly_group_covers_all_records(seeded_engine):
    with Session(seeded_engine) as s:
        hourly = core.records_per_hour(s)
        assert sum(cnt for _, cnt in hourly) == s.query(Record).count()
        # 500 条分钟级记录从 00:00 起 → 每小时 60 条（满桶），首桶整 60
        assert hourly[0][0] == "2026-04-01 00:00" and hourly[0][1] == 60


def test_window_growth_orm_equals_raw_sql(seeded_engine):
    with Session(seeded_engine) as s:
        orm = core.hourly_growth_orm(s)
    raw = core.hourly_growth_raw(seeded_engine)
    assert orm == raw, "窗口函数 ORM 与裸 SQL 必须逐行一致"
    assert orm[0][2] is None and orm[0][3] is None        # 首桶无上期
    # 环比定义校验：growth = cnt/prev - 1
    for hour, cnt, prev, growth in orm[1:]:
        if prev:
            assert abs(growth - round(cnt / prev - 1.0, 4)) < 1e-9


def test_records_per_hour_uses_strftime_not_date_trunc(seeded_engine):
    """SQLite 口径说明：date_trunc 不可用，strftime 路径真实可跑。"""
    with Session(seeded_engine) as s:
        with pytest.raises(Exception):
            s.execute(select(func.date_trunc("hour", Record.ts)))
        assert len(core.records_per_hour(s)) > 1


def test_seed_records_are_on_their_own_devices_points(seeded_engine):
    """溯源的前提是"记录挂对设备"：逐条核对 seed 轮转的 (设备, 指标) 归属。

    回归护栏：曾经用 zip(devices * 2, points) 生成映射，`devices * 2` 是序列
    重复 [D1,D2,D3,D1,D2,D3] 而非逐设备重复 → 记录挂到别的设备测点上，
    平均振动与告警溯源全部错位。
    """
    with Session(seeded_engine) as s:
        recs = s.query(Record).order_by(Record.id).all()
        assert len(recs) == 500
        wrong = []
        for i, r in enumerate(recs):
            want_code = core.DEMO_DEVICES[i % 3][0]
            want_metric = "vib" if i % 2 == 0 else "temp"
            if r.point.device.code != want_code or r.point.metric != want_metric:
                wrong.append((i, r.point.device.code, r.point.metric))
        assert wrong == [], "前 5 条错位: %s" % wrong[:5]


def test_traceability_resolves_every_alarm_to_its_reading(seeded_engine):
    """C层溯源：每条告警都能沿四表 JOIN 反查到同刻振动原始读数，孤儿行 0。"""
    res = core.traceability_check(seeded_engine)
    assert res["alarms_total"] == res["alarms_traced"] > 0
    assert res["orphan_total"] == 0
    assert set(res["orphan_rows"]) == {"records.point_id", "points.device_id",
                                       "alarms.device_id"}
    assert res["join_tables"] == 4
    for alarm_id, code, ts, level, value in res["samples"]:
        assert level in (1, 2) and value > 0 and code.startswith("DEV-")


def test_device_hourly_summary_matches_row_by_row_manual(seeded_engine):
    """A层复杂查询：四表 JOIN 聚合结果必须与 Python 逐行手算逐桶一致。"""
    with Session(seeded_engine) as s:
        sql_rows = core.device_hourly_summary(s)
    manual = core.device_hourly_manual(seeded_engine)
    assert len(sql_rows) == len(manual) == 27         # 3 设备 × 9 个小时桶
    assert core.summary_matches_sql(sql_rows, manual)
    assert sum(r[3] for r in sql_rows) == 500         # 记录数守恒
    total_alarms = core.traceability_check(seeded_engine)["alarms_total"]
    assert sum(r[6] for r in sql_rows) == total_alarms  # 告警数守恒（外连接不重复计数）
    assert core.p3_status_of(2) == "DOWN" and core.p3_status_of(1) == "WARN" \
        and core.p3_status_of(None) == "RUN"


def test_n_plus_one_selectinload_and_lazy_modes(seeded_engine):
    """B层 N+1 取证的可证伪面：三种预加载策略的 SELECT 条数真实不同。"""
    lazy = core.n_plus_one_demo(seeded_engine, loader="lazy")
    joined = core.n_plus_one_demo(seeded_engine, loader="joinedload")
    sel = core.n_plus_one_demo(seeded_engine, loader="selectinload")
    assert lazy["mitigated"] is False and lazy["eager_sql_count"] == lazy["lazy_sql_count"]
    assert joined["mitigated"] is True and joined["eager_sql_count"] == 1
    assert sel["mitigated"] is True and sel["eager_sql_count"] == 2
    assert sel["lazy_sql_count"] == joined["lazy_sql_count"] == 4   # 3 设备 + 1 列表
    with pytest.raises(ValueError):
        core.n_plus_one_demo(seeded_engine, loader="bogus")


def test_p3_handoff_export_matches_contract(seeded_engine, tmp_path):
    """A层闭环交接：导出的 CSV 表头/时间/设备编号必须能被 P3 的读取口径接受。"""
    path = str(tmp_path / "p3_dashboard_handoff.csv")
    stats = core.export_p3_handoff(seeded_engine, path)
    assert stats["rows"] == 27 and stats["columns"] == list(core.P3_CONTRACT_COLUMNS)
    lines = open(path, encoding="utf-8").read().splitlines()
    assert lines[0].strip() == ",".join(core.P3_CONTRACT_COLUMNS)
    check = core.validate_p3_handoff(seeded_engine, path)
    assert check["exists"] and check["missing_columns"] == []
    assert check["ts_parse_failures"] == 0 and check["unknown_devices"] == []
    assert check["empty_cells"] == 0                  # 每桶都有 temp 与 vib
    assert sum(stats["status_counts"].values()) == stats["rows"]


def test_p3_handoff_readable_by_p3_cockpit(seeded_engine, tmp_path):
    """真·闭环取证：直接调用 P3 的 data_source 装载本项目交接文件（只读不改 P3）。

    P3 不在环境里时跳过——不放任"口头达标"：跳过与否不影响 A 层判据本身。
    """
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                       "p33_kpi_cockpit", "src")
    if not os.path.isdir(src):
        pytest.skip("p33_kpi_cockpit 未随本检出提供，无法做消费端验证")
    import sys
    sys.path.insert(0, src)
    try:
        from kpi_cockpit import config as p3cfg
        from kpi_cockpit import data_source as p3ds
    except Exception as exc:                                # noqa: BLE001
        pytest.skip("P3 模块不可导入：%s" % exc)
    path = str(tmp_path / "p3_dashboard_handoff.csv")
    core.export_p3_handoff(seeded_engine, path)
    here = os.path.abspath(os.path.join(src, ".."))
    cfg = p3cfg.load_config(os.path.join(here, "config", "rules.yaml"))
    ds = p3ds.load(cfg, here, source="csv", csv_path=path)
    assert ds.mode == "clean" and len(ds.records) == 27
    assert {c for c in core.P3_CONTRACT_COLUMNS
            if ds.provenance.get(c) == "文件原始"} == set(core.P3_CONTRACT_COLUMNS)
    assert sorted(ds.devices) == ["DEV-01", "DEV-02", "DEV-03"]
