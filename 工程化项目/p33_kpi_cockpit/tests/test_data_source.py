# -*- coding: utf-8 -*-
"""TODO-0 数据源层测试：clean.csv 优先 / 合成兜底 / 列级出处 / 可复现性。

覆盖工单验收：
  C 层「数据源缺失时按种子合成并在报告说明」→ test_load_auto_* / test_synth_*
  B 层「来源与出处逐列写清」                → test_from_clean_provenance_*
"""
import copy
import os

import pytest

from kpi_cockpit import config as C
from kpi_cockpit import data_source as DS

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = os.path.join(HERE, "config", "rules.yaml")


def _cfg(**override):
    """真配置深拷贝 + 定点覆盖（避免测试污染 config/rules.yaml）。"""
    base = copy.deepcopy(C.load_config(REAL).raw)
    for k, v in override.items():
        head, _, tail = k.partition(".")
        if tail:
            base[head][tail] = v
        else:
            base[head] = v
    return C.Settings.from_dict(base)


# ------------------------------------------------------------------ 工具函数边界
def test_parse_ts_accepts_four_formats_and_rejects_garbage():
    assert DS.parse_ts("2026-03-01 08:00:00").month == 3
    assert DS.parse_ts("2026-03-01T08:00:00").hour == 8
    assert DS.parse_ts("2026-03-01 08:00").minute == 0
    assert DS.parse_ts("2026-03-01").day == 1
    with pytest.raises(ValueError):
        DS.parse_ts("not-a-date")


def test_parse_ts_strips_whitespace():
    assert DS.parse_ts("  2026-03-01  ") .year == 2026


@pytest.mark.parametrize("lam,expected", [(0.05, 0), (5.0, 5)])
def test_poisson_mean_follows_lambda(lam, expected):
    import random
    rng = random.Random(7)
    sample = sum(DS.poisson(rng, lam) for _ in range(4000)) / 4000.0
    assert abs(sample - expected) < max(0.6, expected * 0.25)


def test_poisson_is_deterministic_per_seed_and_never_negative():
    import random
    a = [DS.poisson(random.Random(3), 2.0) for _ in range(1)]
    b = [DS.poisson(random.Random(3), 2.0) for _ in range(1)]
    assert a == b
    rng = random.Random(11)
    assert all(DS.poisson(rng, 0.5) >= 0 for _ in range(500))


def test_sha12_is_stable_and_12_hex_chars(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("ts\n2026-03-01 08:00:00\n", encoding="utf-8")
    s1, s2 = DS.sha12(str(p)), DS.sha12(str(p))
    assert s1 == s2 and len(s1) == 12 and int(s1, 16) >= 0


def test_dataset_rejects_empty_source():
    with pytest.raises(ValueError, match="0 行"):
        DS.Dataset([], "空文件", {}, "synth")


def test_dataset_devices_dates_and_as_df():
    ds = DS.Dataset([{"ts": "2026-03-02 08:00:00", "device_id": "B"},
                    {"ts": "2026-03-01 08:00:00", "device_id": "A"}],
                    "x", {}, "synth")
    assert ds.devices == ["A", "B"]
    assert ds.dates == ["2026-03-01", "2026-03-02"]
    df = ds.as_df()                      # pandas 在 pp03 已安装 → 真出 DataFrame
    assert len(df) == 2 and str(df["ts"].dtype).startswith("datetime")


# ------------------------------------------------------------------ 合成兜底路径
def test_synth_records_are_reproducible_and_in_config_bounds():
    cfg = _cfg()
    r1, r2 = DS.synth_records(cfg), DS.synth_records(cfg)
    assert r1 == r2, "同 seed 必须逐行一致（NF-1）"
    assert len(r1) == int(cfg.raw["data"]["synth"]["rows"])
    assert set(r["device_id"] for r in r1) == set(cfg.raw["data"]["synth"]["devices"])
    for r in r1:
        assert 0 <= r["yield_pct"] <= 100
        assert r["ok_qty"] <= r["output"]
        assert r["status"] in ("RUN", "IDLE", "DOWN")


def test_synth_records_change_when_seed_changes():
    assert DS.synth_records(_cfg(seed=99))[:20] != DS.synth_records(_cfg())[:20], \
        "换 seed 必须换数据（否则 seed 是死键）"


def test_synth_line_comes_from_config_ledger():
    recs = DS.synth_records(_cfg())
    assert recs[0]["line"] == "一号产线", "设备→产线应映射 config.lines"


# ------------------------------------------------------------------ clean.csv 归一
def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_from_clean_keeps_file_columns_and_marks_provenance(tmp_path):
    p = _write(tmp_path / "clean.csv",
               "ts,device_id,line,output,ok_qty,temp\n"
               "2026-03-01 08:00:00,DEV-01,一号产线,100,95,60.0\n")
    recs, prov = DS.from_clean(p, DS.read_csv_rows(p), _cfg())
    assert recs[0]["output"] == 100 and recs[0]["temp"] == 60.0
    assert recs[0]["yield_pct"] == 95.0, "良率缺列时按 ok_qty/output 派生"
    assert prov["ts"] == "文件原始" and prov["yield_pct"] == "派生·ok_qty/output"
    assert prov["status"] == "派生·阈值判定"
    assert prov["vib"].startswith("合成·seed="), "文件没有的列必须诚实标合成"


def test_from_clean_handles_minimal_schema_only_ts(tmp_path):
    p = _write(tmp_path / "min.csv", "ts\n2026-03-01 08:00:00\n2026-03-01 08:30:00\n")
    rows = DS.read_csv_rows(p)
    recs, prov = DS.from_clean(p, rows, _cfg())
    assert len(recs) == 2
    assert recs[0]["device_id"] == "DEV-01" and recs[1]["device_id"] == "DEV-02"
    assert prov["device_id"] == "派生·按行序轮询设备表"
    assert all(r["ok_qty"] <= r["output"] for r in recs)


def test_from_clean_clamps_bad_ok_qty(tmp_path):
    p = _write(tmp_path / "bad.csv",
               "ts,ok_qty,output\n2026-03-01 08:00:00,300,100\n")
    recs, _ = DS.from_clean(p, DS.read_csv_rows(p), _cfg())
    assert recs[0]["ok_qty"] == 100 and recs[0]["yield_pct"] == 100.0


# ------------------------------------------------------------------ 选源策略
def test_usable_rejects_missing_columns_and_bad_ts(tmp_path):
    cfg = _cfg()
    assert DS._usable(str(tmp_path / "nope.csv"), cfg) is None
    p1 = _write(tmp_path / "nocols.csv", "a,b\n1,2\n")
    assert DS._usable(p1, cfg) is None, "缺 ts 列不可用"
    p2 = _write(tmp_path / "badds.csv", "ts\n昨天\n")
    assert DS._usable(p2, cfg) is None, "时间不可解析不可用"
    p3 = _write(tmp_path / "empty.csv", "ts\n")
    assert DS._usable(p3, cfg) is None, "0 行数据不可用"


def test_load_auto_prefers_clean_csv_over_synth(tmp_path):
    cfg = _cfg(**{"data.candidates": [str(tmp_path / "clean.csv")]})
    p = _write(tmp_path / "clean.csv",
               "ts,output,ok_qty\n2026-03-01 08:00:00,10,9\n2026-03-01 08:30:00,20,18\n")
    ds = DS.load(cfg, HERE, source="auto")
    assert ds.mode == "clean"
    assert "P2.1 清洁产出" in ds.source and "sha256=" in ds.source
    assert len(ds.records) == 2


def test_load_auto_falls_back_to_synth_and_says_so(tmp_path):
    cfg = _cfg(**{"data.candidates": [str(tmp_path / "absent.csv")]})
    ds = DS.load(cfg, HERE, source="auto")
    assert ds.mode == "synth"
    assert "未找到 clean.csv" in ds.source and "seed=2026" in ds.source


def test_load_source_clean_raises_instead_of_silently_degrading(tmp_path):
    cfg = _cfg(**{"data.candidates": [str(tmp_path / "absent.csv")]})
    with pytest.raises(FileNotFoundError, match="clean.csv"):
        DS.load(cfg, HERE, source="clean")


def test_load_source_csv_requires_path():
    with pytest.raises(ValueError, match="--csv"):
        DS.load(_cfg(), HERE, source="csv")


def test_load_source_csv_rejects_unusable_file(tmp_path):
    p = _write(tmp_path / "x.csv", "foo\n1\n")
    with pytest.raises(ValueError, match="CSV 不可用"):
        DS.load(_cfg(), HERE, source="csv", csv_path=p)


def test_load_source_csv_uses_given_file(tmp_path):
    p = _write(tmp_path / "x.csv", "ts,output,ok_qty\n2026-03-01,5,4\n")
    ds = DS.load(_cfg(), HERE, source="csv", csv_path=p)
    assert ds.mode == "clean" and "外部 CSV" in ds.source
    assert ds.records[0]["output"] == 5


def test_load_source_synth_never_touches_files():
    ds = DS.load(_cfg(), HERE, source="synth")
    assert ds.mode == "synth" and ds.records
    assert set(ds.provenance) == set(DS.CANON), "每列都要有出处标注"
