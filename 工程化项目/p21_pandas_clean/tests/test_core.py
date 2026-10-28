# -*- coding: utf-8 -*-
"""核心层测试：真实纯函数 API（generate_raw / run_pipeline / dedupe / score / gate / validate）。

覆盖工单要求的三档：正常（七步管道清洗+评分+门禁）、边界（空表、恰好压线）、
异常（缺必需列拒收、越界校验中断、strict_validate 开关）。
"""
import os

import pandas as pd
import pytest

from pd_clean import core, pipeline
from pd_clean.config import Settings, load_config

CFG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "rules.yaml")


@pytest.fixture(scope="module")
def cfg():
    return load_config(CFG_PATH)


@pytest.fixture(scope="module")
def cleaned(cfg):
    raw = core.generate_raw(n=200, seed=cfg.seed)
    return raw, pipeline.run_pipeline(raw.copy(), cfg)


def _out_of_range_frame(cfg):
    return pd.DataFrame({
        cfg.s("pipeline.id_column"): ["DEV-01"],
        cfg.s("pipeline.ts_column"): pd.to_datetime(["2026-03-01 08:00:00"]),
        cfg.s("pipeline.temp_column"): [cfg.f("pipeline.temp_max") + 1.0],
        cfg.s("pipeline.press_column"): [0.5],
        cfg.s("pipeline.status_column"): ["RUN"],
    })


def test_generate_raw_is_seeded_and_dirty(cfg):
    a = core.generate_raw(n=120, seed=cfg.seed)
    b = core.generate_raw(n=120, seed=cfg.seed)
    pd.testing.assert_frame_equal(a, b)
    assert list(a.columns) == cfg.lst("pipeline.required_columns")
    assert len(a) > 120
    assert int(a[cfg.s("pipeline.temp_column")].astype(str)
               .isin(["N/A", ""]).sum()) > 0


def test_clean_reduces_rows_and_removes_bad(cleaned, cfg):
    raw, res = cleaned
    clean = res["clean"]
    assert len(clean) < len(raw)
    assert clean[cfg.s("pipeline.temp_column")].between(
        cfg.f("pipeline.temp_min"), cfg.f("pipeline.temp_max")).all()
    assert clean[cfg.s("pipeline.press_column")].between(
        cfg.f("pipeline.press_min"), cfg.f("pipeline.press_max")).all()
    assert pd.api.types.is_datetime64_any_dtype(clean[cfg.s("pipeline.ts_column")])
    body = clean.drop(columns=[cfg.s("pipeline.warning_column"),
                               cfg.s("pipeline.danger_column")])
    assert int(body.isna().sum().sum()) == 0
    assert res["dup_rate"] == 0.0
    assert all(a["rows_out"] <= a["rows_in"] for a in res["audits"])


def test_clean_is_deduped(cfg):
    df = pd.DataFrame({
        cfg.s("pipeline.id_column"): ["DEV-01", "DEV-01", "DEV-02"],
        cfg.s("pipeline.ts_column"): pd.to_datetime(["2026-03-01 08:00:00"] * 3),
        cfg.s("pipeline.temp_column"): [60.0, 61.0, 62.0],
        cfg.s("pipeline.press_column"): [0.4, 0.5, 0.6],
    })
    out, audit = core.dedupe(df, cfg)
    assert len(out) == 2
    assert audit["rows_in"] == 3 and audit["rows_out"] == 2 and audit["removed"] == 1
    assert out[cfg.s("pipeline.id_column")].tolist() == ["DEV-01", "DEV-02"]
    assert int(out.duplicated(subset=cfg.lst("pipeline.dedupe_subset")).sum()) == 0


def test_quality_score_in_range_and_above_target(cleaned, cfg):
    _, res = cleaned
    value = res["score"]
    parts = res["score_parts"]
    gates = cfg.get("quality.gates")
    assert 0.0 <= value <= 100.0
    assert value >= float(gates["pass"])
    assert set(parts) == set(cfg.get("quality.weights"))
    assert abs(sum(float(v) for v in parts.values()) - value) <= 0.1


def test_gate_true_when_above_target(cfg):
    gates = cfg.get("quality.gates")
    top = core.gate(float(gates["excellent"]), cfg)
    assert top["tier_D_pass"] is True
    assert top["tier_C_good"] is True
    assert top["tier_B_excellent"] is True
    at_line = core.gate(float(gates["pass"]), cfg)
    assert at_line["tier_D_pass"] is True
    assert at_line["tier_C_good"] is False


def test_gate_false_when_below_target(cfg):
    gates = cfg.get("quality.gates")
    low = core.gate(float(gates["pass"]) - 1.0, cfg)
    assert low["tier_D_pass"] is False
    assert low["tier_C_good"] is False
    assert low["tier_B_excellent"] is False
    assert low["target"] == float(gates["pass"])
    assert low["score"] == float(gates["pass"]) - 1.0


def test_empty_frame_quality_zero(cfg):
    empty = pd.DataFrame({c: [] for c in cfg.lst("pipeline.required_columns")})
    value, parts = core.score(empty, cfg)
    assert value == 0.0
    assert parts == {k: 0.0 for k in cfg.get("quality.weights")}
    assert core.gate(value, cfg)["tier_D_pass"] is False


def test_empty_slice_of_clean_frame_scores_zero(cfg):
    raw = core.generate_raw(n=60, seed=cfg.seed)
    res = pipeline.run_pipeline(raw.copy(), cfg)
    empty = res["clean"].iloc[0:0]
    assert core.score(empty, cfg)[0] == 0.0


def test_inspect_schema_rejects_missing_required_columns(cfg):
    with pytest.raises(core.PipelineError):
        core.inspect_schema(pd.DataFrame({"vib": [1.0], "temp": [60.0]}), cfg)


def test_validate_raises_when_process_range_broken(cfg):
    with pytest.raises(core.QualityError):
        core.validate(_out_of_range_frame(cfg), cfg)


def test_validate_only_warns_when_strict_off():
    loose = Settings.from_dict({"pipeline": {"strict_validate": False}})
    checks, audit, _dup = core.validate(_out_of_range_frame(loose), loose)
    key = "%s∈[%s,%s]" % (loose.s("pipeline.temp_column"),
                         loose.f("pipeline.temp_min"),
                         loose.f("pipeline.temp_max"))
    assert checks[key] is False
    assert any("strict_validate=false" in d for d in audit["detail"])
    assert audit["removed"] == 0
