# -*- coding: utf-8 -*-
"""ORM 模型层测试（B层·四表建模 + 外键约束 + relationship 往返）。"""
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from warehouse_orm import core
from warehouse_orm.models import Device, Record, SensorPoint


@pytest.fixture()
def engine(tmp_path):
    eng = core.make_engine("sqlite:///%s" % (tmp_path / "wh.db"))
    core.init_db(eng)
    return eng


def test_four_tables_created(engine):
    assert set(["devices", "points", "records", "alarms"]) <= set(
        inspect(engine).get_table_names())


def test_composite_index_declared_in_table_args(engine):
    idx = {i["name"]: i["column_names"] for i in inspect(engine).get_indexes("records")}
    assert "idx_dev_ts" in idx
    assert idx["idx_dev_ts"] == ["point_id", "ts"]


def test_device_area_column(engine):
    cols = {c["name"] for c in inspect(engine).get_columns("devices")}
    assert "area" in cols


def test_relationship_roundtrip(engine):
    with Session(engine) as s:
        d = Device(code="DEV-9", name="试验机", area="车间Z")
        p = SensorPoint(metric="vib", unit="mm/s", device=d)
        s.add_all([d, p])
        s.commit()
    with Session(engine) as s:
        got = s.query(Device).filter_by(code="DEV-9").one()
        assert [pt.metric for pt in got.points] == ["vib"]      # 一对多下行
        assert got.points[0].device.code == "DEV-9"             # 反向回指


def test_fk_orphan_rejected_by_database(engine):
    """外键约束强制：孤儿测点指向不存在的设备必须被库拒绝。"""
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text("INSERT INTO points(device_id, metric, unit) "
                           "VALUES (999999, 'vib', 'mm/s')"))
    assert core.integrity_check(engine)["orphan_rejected"] is True


def test_cascade_delete_device_removes_children(engine):
    with Session(engine) as s:
        d = Device(code="DEV-C", name="拆机", area="车间Q")
        p = SensorPoint(metric="temp", unit="℃", device=d)
        s.add_all([d, p])
        s.commit()
        pid = p.id
        s.delete(d)
        s.commit()
        assert s.query(SensorPoint).filter_by(id=pid).first() is None


def test_record_ts_stored_as_datetime(engine):
    """避坑口径：时间戳列是 DateTime，不是字符串；存取往返后仍是 datetime 对象。"""
    import datetime as dt
    col_types = {c["name"]: str(c["type"]) for c in inspect(engine).get_columns("records")}
    assert col_types["ts"].upper().startswith("DATETIME")
    with Session(engine) as s:
        d = Device(code="DEV-T", name="时钟机", area="车间T")
        p = SensorPoint(metric="vib", unit="mm/s", device=d)
        s.add_all([d, p])
        s.flush()
        s.add(Record(point_id=p.id, ts=dt.datetime(2026, 5, 1, 3, 4, 5), value=1.5))
        s.commit()
        r = s.query(Record).one()
        assert isinstance(r.ts, dt.datetime) and r.ts.hour == 3
