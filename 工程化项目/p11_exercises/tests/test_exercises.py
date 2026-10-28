# -*- coding: utf-8 -*-
"""exercises 层测试：一题一函数、配置驱动、输出契约统一。

对应 docs/04 用例 TC-E01~TC-E05；重点验证"配置改了结果真的变"。
"""
from exercise_five import config, exercises

REQUIRED_KEYS = {"number", "title", "lines", "payload"}


def test_exercise_result_contract(cfg, files):
    """五个函数返回同一契约（报告层因此无需为每题写特例）。"""
    runs = [exercises.exercise1(cfg), exercises.exercise2(cfg),
            exercises.exercise3(cfg), exercises.exercise4(cfg),
            exercises.exercise5(cfg, files)]
    for run_ in runs:
        assert REQUIRED_KEYS <= set(run_), run_["number"]
        assert run_["lines"], run_["number"]


def test_exercise1_change_config_changes_output(cfg, tmp_path):
    """改配置不改代码：换样本与阈值后，输出行数量与定级随之变化。"""
    base_samples = list(cfg.temperature["samples"])
    path = tmp_path / "x.yaml"
    path.write_text("temperature:\n  samples: [25.0]\n"
                    "warn: 10.0\ndanger: 20.0\n", encoding="utf-8")
    other = config.load_config(str(path))
    run_base = exercises.exercise1(cfg)
    run_other = exercises.exercise1(other)
    assert len(run_other["payload"]["rows"]) == 1
    assert len(run_base["payload"]["rows"]) == len(base_samples)
    assert run_other["payload"]["rows"][0]["level"] == "危险"


def test_exercise3_reports_effective_delete(cfg):
    """题3 回归：报告行必须写明"删除后 N-1 台"，与 payload 一致。"""
    run_ = exercises.exercise3(cfg)
    payload = run_["payload"]
    assert any("删除生效" in line for line in run_["lines"])
    assert payload["after"] == payload["before"] - 1


def test_exercise4_uses_configured_device_id(cfg):
    """题4：PLC 的 ID 由配置设备清单键提供，非硬编码。"""
    run_ = exercises.exercise4(cfg)
    assert run_["payload"]["plc"]["dev_id"] == cfg.device_key(
        cfg.plc["dev_id"])
    assert run_["payload"]["plc"]["scan_ms"] == int(cfg.plc["scan_ms"])


def test_exercise5_probes_all_error_branches(cfg, files):
    """题5：五种输入形态各自返回约定标记。"""
    run_ = exercises.exercise5(cfg, files)
    probes = run_["payload"]["probes"]
    assert probes["缺失"] == "FILE_NOT_FOUND"
    assert probes["坏编码"] == "BAD_ENCODING"
    assert probes["目录"] == "IS_DIRECTORY"
    assert probes["空输入"] == "EMPTY_PATH"
    assert probes["空输入(None)"] == "EMPTY_PATH"
    assert probes["正常"] == str(cfg.reader["sample_text"])


def test_exercise3_missing_update_id_raises(cfg, tmp_path):
    """异常档：配置指向不存在的设备键时直接报错（不静默跳过）。"""
    path = tmp_path / "bad.yaml"
    path.write_text("devices:\n  update_id: 99\n  remove_id: 2\n"
                    "warn: 80.0\ndanger: 95.0\n", encoding="utf-8")
    other = config.load_config(str(path))
    try:
        exercises.exercise3(other)
    except ValueError as exc:
        assert "update_id" in str(exc)
    else:
        raise AssertionError("配置指向不存在设备时应报错")
