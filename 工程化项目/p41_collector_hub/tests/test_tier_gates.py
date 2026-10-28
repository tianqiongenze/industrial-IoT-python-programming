# -*- coding: utf-8 -*-
"""分层工单闸门（D/C/B/A）测试：在真实流水线上逐条拿出达标证据，而不是只查文件。"""
import json
import os

from collector_hub import config as C
from collector_hub import core
from collector_hub import pipeline

CFG = os.path.join(os.path.dirname(__file__), "..", "config", "rules.yaml")


def _run(cfg, out_dir):
    sections = pipeline.run(cfg, str(out_dir))
    data = json.loads(open(os.path.join(str(out_dir), "result.json"),
                           encoding="utf-8").read())
    text = open(os.path.join(str(out_dir), "report.txt"), encoding="utf-8").read()
    return data, text, sections


def test_d_layer_pipeline_runs_and_reconciles(tmp_path):
    data, text, _ = _run(C.load_config(CFG), tmp_path)
    assert data["reconcile"]["ok"] is True
    assert data["planned"] == data["apm"]["planned"] == 36
    assert "D层 基础贯通" in text
    assert data["tiers"]["D"] is True


def test_c_layer_three_sources_and_rate_above_target(tmp_path):
    cfg = C.load_config(CFG)
    data, text, _ = _run(cfg, tmp_path)
    assert len(cfg.raw["sources"]) >= 3
    assert sorted(data["sources"]) == ["PLC1", "PLC2", "PLC3"]
    assert data["collection_rate"] > 95.0
    assert "采集率 97.22%" in text
    assert data["tiers"]["C"] is True


def test_b_layer_reconnect_is_what_moves_the_rate(tmp_path):
    data, text, _ = _run(C.load_config(CFG), tmp_path)
    assert data["injected_faults"] == 3
    assert data["apm_no_retry"]["drop"] > data["apm"]["drop"] > 0
    assert data["apm"]["retry"] > 0
    assert data["rate_no_retry"] < data["rate_target"] < data["collection_rate"]
    assert "[链路可靠性对照（B层·断线重连实测）]" in text
    assert data["tiers"]["B"] is True


def test_a_layer_apm_panel_is_self_consistent(tmp_path):
    data, text, _ = _run(C.load_config(CFG), tmp_path)
    apm = data["apm"]
    for key in ("planned", "ok", "drop", "retry", "calls", "latency_ms", "rate",
                "avg_ms", "backoff_ms", "max_wait_ms"):
        assert key in apm, key
    assert data["identities"] == {"ok+drop==planned": True,
                                  "calls==ok+drop+retry": True}
    assert round(core.rate(apm["ok"], apm["planned"]), 4) == data["collection_rate"]
    assert "[APM 面板（A层）]" in text
    assert "丢弃" in text and "延迟" in text
    assert data["tiers"]["A"] is True


def test_report_and_json_agree_on_every_counter(tmp_path):
    data, text, sections = _run(C.load_config(CFG), tmp_path)
    apm = data["apm"]
    panel = dict(sections)["APM 面板（A层）"]
    assert ("计划 %d ｜ 成功 %d ｜ 丢弃 %d ｜ 重试 %d ｜ 传输调用 %d"
            % (apm["planned"], apm["ok"], apm["drop"], apm["retry"],
               apm["calls"])) in panel
    assert "采集率 %.2f%%" % apm["rate"] in panel[1]
    for line in panel:
        assert line in text


def test_config_only_change_can_fail_the_gate(tmp_path):
    """改配置不改代码：把重连上限调到 0，C/B 层闸门必须立刻判不达标。"""
    text = open(CFG, encoding="utf-8").read().replace("retry_limit: 3", "retry_limit: 0")
    p = tmp_path / "rules.yaml"
    p.write_text(text, encoding="utf-8")
    data, _, _ = _run(C.load_config(str(p)), tmp_path / "out")
    assert data["apm"]["retry"] == 0
    assert data["apm_no_retry"] == data["apm"]
    assert data["collection_rate"] < 95.0
    assert data["tiers"]["C"] is False and data["tiers"]["B"] is False
    assert data["tiers"]["D"] is True


def test_no_fault_injection_reaches_full_collection(tmp_path):
    """故障全部撤掉 → 采集率 100%，丢弃 0，重连 0（面板不退化成硬编码）。"""
    text = open(CFG, encoding="utf-8").read().replace("fail_attempts: 2", "fail_attempts: 0")
    text = text.replace("fail_attempts: 4", "fail_attempts: 0")
    p = tmp_path / "rules.yaml"
    p.write_text(text, encoding="utf-8")
    data, _, _ = _run(C.load_config(str(p)), tmp_path / "out")
    assert data["apm"]["drop"] == 0 and data["apm"]["retry"] == 0
    assert data["collection_rate"] == 100.0
    assert data["tiers"]["B"] is False     # 无故障可挽回，B 层证据不成立


def test_run_is_reproducible(tmp_path):
    """同一配置跑两遍：APM 计数逐字段相等（延迟为配置推导值，不含墙钟）。"""
    a, _, _ = _run(C.load_config(CFG), tmp_path / "a")
    b, _, _ = _run(C.load_config(CFG), tmp_path / "b")
    assert a["apm"] == b["apm"]
    assert a["per_source"] == b["per_source"]
    assert a["tiers"] == b["tiers"]
