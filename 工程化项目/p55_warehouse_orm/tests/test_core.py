# -*- coding: utf-8 -*-
import pytest

from warehouse_orm import core


@pytest.fixture
def tbl():
    t = core.Table("t", ["device_id", "temp"])
    for i in range(5):
        t.insert({"device_id": "DEV-01" if i % 2 else "DEV-02", "temp": float(i)})
    t.create_index("device_id")
    return t


def test_insert_requires_all_fields():
    t = core.Table("t", ["a", "b"])
    with pytest.raises(ValueError):
        t.insert({"a": 1})


def test_table_requires_fields():
    with pytest.raises(ValueError):
        core.Table("t", [])


def test_where_with_index_uses_index(tbl):
    assert tbl.explain(device_id="DEV-01") == "INDEX SCAN on device_id"


def test_where_without_index_full_scan(tbl):
    assert tbl.explain(temp=3.0) == "FULL SCAN on t"


def test_index_query_correct(tbl):
    got = tbl.where(device_id="DEV-02")
    assert len(got) == 3 and all(r["device_id"] == "DEV-02" for r in got)


def test_full_scan_correct(tbl):
    assert len(tbl.where(temp=3.0)) == 1


def test_create_index_unknown_col(tbl):
    with pytest.raises(ValueError):
        tbl.create_index("nope")


def test_index_maintained_after_insert():
    t = core.Table("t", ["k", "v"])
    t.create_index("k")
    t.insert({"k": "a", "v": 1})
    assert len(t.where(k="a")) == 1
