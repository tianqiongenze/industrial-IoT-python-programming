# -*- coding: utf-8 -*-
"""工单 P2.1 四行档位回归（D 及格 / C 良好 / B 优秀 / A 超优）。

原则：每条判定都对着 tmp 目录里的真实运行断言，不做文案复读；
D/C/B 各配一个**只改 config/rules.yaml（不动任何代码）**的翻转用例，
证明三道闸真的会咬；A 档的增量断言是硬断言——增量重放后的 clean.csv
必须与全量运行**逐字节一致**。report.txt 第 15 节 ↔ result.json 的
`tiers` 也逐条比对，防止报告与结构化结果两张皮。
"""
import json
import os
import re
from datetime import datetime, timedelta

import pandas as pd
import pytest

from pd_clean import core, io_utils, pipeline, stylecheck
from pd_clean.config import load_config

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RULES_PATH = os.path.join(ROOT, "config", "rules.yaml")
REAL_INPUT = os.path.abspath(os.path.join(ROOT, "..", "..", "p21_raw.csv"))
TIER_KEYS = {"D档": "tier_D_pass", "C档": "tier_C_good",
             "B档": "tier_B_excellent", "A档": "tier_A_super"}


def _rules_text():
    return io_utils.read_text(RULES_PATH)


def _cfg_file(tmp_path, name, *pairs):
    """rules.yaml 文本级改写＝只改配置不改代码；返回 load_config 结果。"""
    text = _rules_text()
    for old, new in pairs:
        assert old in text, "翻转目标 %r 不在 rules.yaml 中" % old
        text = text.replace(old, new, 1)
    path = os.path.join(str(tmp_path), name)
    io_utils.write_text(path, text)
    return load_config(path)


def _run(cfg, tmp_path, input_path=None, bench=False):
    """真实全流程跑进 tmp 目录，返回 (result.json 字典, report.txt 文本)。"""
    pipeline.run(cfg, str(tmp_path), input_path=input_path or REAL_INPUT,
                 bench=bench)
    result = json.loads(io_utils.read_text(os.path.join(str(tmp_path),
                                                        "result.json")))
    report_text = io_utils.read_text(os.path.join(str(tmp_path), "report.txt"))
    return result, report_text


def _tier_line(report_text, prefix):
    lines = [ln for ln in report_text.splitlines() if ln.startswith(prefix)]
    assert len(lines) == 1, "%s 应恰有一行档位判定" % prefix
    return lines[0]


def _crafted_raw(tmp_path):
    """构造 200 行、含 1 个非法 device_id 的输入：实测质量分 99.9（<100），
    用于演示 quality.gates 三道线（85/88/90→100）真的按实测分数咬合。"""
    start = datetime(2026, 3, 1)
    rows = []
    for i in range(200):
        dev = "XX-01" if i == 123 else "DEV-%02d" % (i % 4 + 1)
        rows.append([dev, (start + timedelta(minutes=5 * i))
                     .strftime("%Y-%m-%d %H:%M:%S"),
                     50.0 + (i % 21), 0.5, "RUN"])
    path = os.path.join(str(tmp_path), "crafted.csv")
    pd.DataFrame(rows, columns=["device_id", "ts", "temp", "press", "status"]
                 ).to_csv(path, index=False)
    return path


# ------------------------------------------------------------------ D/C/B/A 实测
def test_full_run_workorder_tiers_and_report_json_agreement(tmp_path):
    """真实输入全量跑（--no-bench 口径）：D/C/B 达标；A 因未压测诚实未达；
    第 15 节逐档判定文字与 result.json 的 tiers 一一对齐。"""
    result, report_text = _run(_cfg_file(tmp_path, "rules.yaml"), tmp_path)
    t = result["tiers"]
    assert t["tier_D_pass"] and t["tier_C_good"] and t["tier_B_excellent"]
    assert t["tier_A_super"] is False and t["bench_measured"] is False
    assert t["pipeline_steps"] == core.EXPECTED_AUDIT_STEPS
    assert t["log_reproducible"] is True
    assert t["incremental_matches_full"] is True
    assert t["usage_example"] is True
    assert t["pep8_score"] >= t["pep8_min_B"] >= t["pep8_min_D"]
    for prefix, key in TIER_KEYS.items():
        line = _tier_line(report_text, prefix)
        assert ("→ 达标" in line) == t[key], line
    assert "保底自检（不计入工单档位）" in report_text
    for legacy in ("学徒", "操作员", "组长", "师傅"):
        assert legacy not in report_text       # 不再借用课堂笔记本的字母梯子


def test_workorder_rows_are_quoted_verbatim(tmp_path):
    """第 15 节每档行首必须逐字复述工单《P2.1》「验收标准」四行原文。

    口径与 p11/p41 一致：工单原文一格不许改（哪怕只是加个空格），rules.yaml 抬起后的
    实际线值只许出现在证据段。这里直接读课程仓库里的工单文件对表，
    `pipeline.WO_ROW` 常量与报告两处一起锁——常量漂了、报告漂了都会红。
    """
    wo = os.path.abspath(os.path.join(ROOT, "..", "..", "工单任务书",
                                      "P2.1工单-Pandas数据处理管道.md"))
    if not os.path.exists(wo):
        pytest.skip("工单任务书不在仓库内的相对位置（项目被单独拷走时）")
    rows = {}
    for line in io_utils.read_text(wo).splitlines():
        m = re.match(r"^\|\s*(及格\(D\)|良好\(C\)|优秀\(B\)|超优\(A\))\s*\|"
                     r"\s*(.+?)\s*\|\s*$", line.strip())
        if m:
            rows[m.group(1).split("(")[1][:-1]] = m.group(2)
    assert sorted(rows) == ["A", "B", "C", "D"], rows
    assert pipeline.WO_ROW == rows, (pipeline.WO_ROW, rows)
    _, report_text = _run(_cfg_file(tmp_path, "rules.yaml"), tmp_path)
    name = {"D": "及格", "C": "良好", "B": "优秀", "A": "超优"}
    for letter, row in rows.items():
        line = _tier_line(report_text, "%s档 " % letter)
        assert line.startswith("%s档 %s「%s」: " % (letter, name[letter], row)), line


def test_real_run_with_bench_lifts_tier_A(tmp_path):
    """A 档整跑：默认口径带 100 万行压测 → 四行全达标（压测约 20s）。"""
    result, report_text = _run(_cfg_file(tmp_path, "rules.yaml"), tmp_path,
                               bench=True)
    t = result["tiers"]
    assert t["bench_measured"] is True and t["bench_pass"] is True
    assert t["tier_A_super"] is True
    assert _tier_line(report_text, "A档").endswith("→ 达标")
    bench_json = json.loads(io_utils.read_text(os.path.join(ROOT, "runtime",
                                                            "bench.json")))
    assert bench_json["bench_rows"] >= 1000000
    assert bench_json["seconds"] < bench_json["budget_seconds"]


def test_pep8_subset_measured_not_fabricated():
    """PEP 8 分数必须由 stylecheck 对包源码实测：真实计数自洽且非满分。"""
    summary = stylecheck.summarize(ROOT)
    assert summary["checked_files"] >= 10
    assert 0.0 < summary["score"] < 100.0      # 真实测量：给编造留不出余地
    assert summary["passed"] + len(summary["violations"]) == summary["total"]


# ------------------------------------------------------------------ C：日志可复现
def test_reproducible_log_second_run_identical():
    """C 档硬断言：同进程二次跑同一输入，逐步行数增量与 clean_log 逐字节一致。"""
    cfg = load_config(RULES_PATH)
    df, _ = pipeline.load_raw(REAL_INPUT, cfg)
    res = pipeline.run_pipeline(df, cfg)
    check = pipeline.reproducibility_check(res, cfg, REAL_INPUT)
    assert check["log_reproducible"] is True
    assert check["deltas_equal"] is True and check["log_identical"] is True
    assert check["steps"] == core.EXPECTED_AUDIT_STEPS
    assert all(a["rows_out"] <= a["rows_in"] for a in res["audits"])


def test_c_gate_flips_on_config_only(tmp_path):
    """只改配置（good 88→100）即可让 C 档从达标翻为未达，且不误伤 D。"""
    crafted = _crafted_raw(tmp_path)
    loose = _cfg_file(tmp_path, "base.yaml",
                      ("strict_validate: true", "strict_validate: false"))
    result, report_text = _run(loose, tmp_path, input_path=crafted)
    assert result["quality_score"] == pytest.approx(99.9)
    assert result["tiers"]["tier_C_good"] is True
    flipped = _cfg_file(tmp_path, "flip.yaml",
                        ("strict_validate: true", "strict_validate: false"),
                        ("    good: 88", "    good: 100"))
    result2, report2 = _run(flipped, tmp_path, input_path=crafted)
    assert result2["tiers"]["log_reproducible"] is True     # 复现子条件仍成立
    assert result2["tiers"]["tier_C_good"] is False          # 分数线咬合生效
    assert result2["tiers"]["tier_D_pass"] is True
    assert "→ 未达" in _tier_line(report2, "C档")
    assert "→ 达标" in _tier_line(report_text, "C档")


# ------------------------------------------------------------------ D：翻转咬合
def test_d_gate_flips_on_config_only(tmp_path):
    """只改配置（pass 85→100）：99.9 分的实测输出立即掉出 D 档。"""
    crafted = _crafted_raw(tmp_path)
    loose = _cfg_file(tmp_path, "base.yaml",
                      ("strict_validate: true", "strict_validate: false"))
    result, report_text = _run(loose, tmp_path, input_path=crafted)
    assert result["tiers"]["tier_D_pass"] is True
    flipped = _cfg_file(tmp_path, "flip.yaml",
                        ("strict_validate: true", "strict_validate: false"),
                        ("    pass: 85", "    pass: 100"))
    result2, report2 = _run(flipped, tmp_path, input_path=crafted)
    assert result2["tiers"]["tier_D_pass"] is False
    assert "→ 未达" in _tier_line(report2, "D档")
    assert "→ 达标" in _tier_line(report_text, "D档")


# ------------------------------------------------------------------ B：翻转咬合
def test_b_gate_flips_on_config_only(tmp_path):
    """两条翻转都只动配置：excellent 90→100（分数线）与
    pep8_pass_rate_high 85→99.9（规范线，实测 <99.9）各咬一次 B；
    C 档不受牵连，A 档因依赖 B 档同步掉线。"""
    crafted = _crafted_raw(tmp_path)
    loose = _cfg_file(tmp_path, "base.yaml",
                      ("strict_validate: true", "strict_validate: false"))
    result, _ = _run(loose, tmp_path, input_path=crafted)
    assert result["tiers"]["tier_B_excellent"] is True
    flip_q = _cfg_file(tmp_path, "q.yaml",
                       ("strict_validate: true", "strict_validate: false"),
                       ("    excellent: 90", "    excellent: 100"))
    rq, _ = _run(flip_q, tmp_path, input_path=crafted)
    assert rq["tiers"]["tier_B_excellent"] is False
    assert rq["tiers"]["tier_C_good"] is True
    flip_p = _cfg_file(tmp_path, "p.yaml",
                       ("pep8_pass_rate_high: 85.0",
                        "pep8_pass_rate_high: 99.9"))
    rp, report_p = _run(flip_p, tmp_path)
    assert rp["tiers"]["pep8_pass_B"] is False
    assert rp["tiers"]["tier_B_excellent"] is False
    assert rp["tiers"]["tier_C_good"] is True
    assert rp["tiers"]["tier_A_super"] is False
    assert "→ 未达" in _tier_line(report_p, "B档")


# ------------------------------------------------------------------ B：使用示例
def test_usage_example_executes(monkeypatch, capsys):
    """README 第六节的使用示例必须能被逐字执行（B 档声明的防腐烂锁）。"""
    readme = io_utils.read_text(os.path.join(ROOT, "README.md"))
    found = core.find_usage_example(readme, "README.md")
    assert found["found"] is True and found["ref"].startswith("README.md:")
    first_line = int(found["ref"].split(":")[1])
    assert readme.splitlines()[first_line - 1] == found["code"].splitlines()[0]
    monkeypatch.chdir(ROOT)
    namespace = {"__name__": "__usage_example__"}
    exec(found["code"], namespace)              # 真实 API，非 mock
    out = capsys.readouterr().out
    assert "清洗:" in out and "质量及格线判定:" in out
    res = namespace["res"]
    assert len(res["clean"]) < res["raw_rows"]
    assert res["score"] >= 0.0


def test_usage_evidence_wired_into_b_gate(tmp_path):
    """pipeline 闸门指向的就是 README.md:行号，报告 B 档行原样引用。"""
    result, report_text = _run(_cfg_file(tmp_path, "rules.yaml"), tmp_path)
    ref = result["tiers"]["usage_example_ref"]
    assert ref.startswith("README.md:")
    assert ref in _tier_line(report_text, "B档")


# ------------------------------------------------------------------ A：增量硬断言
def test_incremental_replay_yields_byte_identical_clean(tmp_path):
    """全量运行后按基线重放同一输入：增量 0 行，clean.csv 逐字节不变。"""
    cfg = load_config(RULES_PATH)
    pipeline.run(cfg, str(tmp_path), input_path=REAL_INPUT, bench=False)
    clean_path = os.path.join(str(tmp_path), "clean.csv")
    with open(clean_path, "rb") as fh:
        before = fh.read()
    sections, info = pipeline.run_incremental(cfg, str(tmp_path), REAL_INPUT)
    assert info["new_rows"] == 0
    assert info["clean_after"] == info["clean_before"]
    with open(clean_path, "rb") as fh:
        assert fh.read() == before
    assert any("幂等重放" in line for _name, lines in sections for line in lines)


def test_custom_rules_bite_when_flipped_and_report_per_step(tmp_path):
    """自定义验证规则是真实闸门：只加一条 YAML 规则 → 对应步骤剔行并在
    第 8 节逐条计数，tiers.custom_rules_removed 与台账同步。"""
    _result, report_text = _run(_cfg_file(tmp_path, "rules.yaml"), tmp_path)
    strict = _cfg_file(tmp_path, "strict.yaml",
                       ('    - "status != \'OFF\'"',
                        '    - "status != \'OFF\'"\n    - "temp <= 55"'))
    result2, report2 = _run(strict, tmp_path)
    assert result2["tiers"]["custom_rules_removed"] > 0
    assert "规则 [temp <= 55] 剔除 0 行" not in report2
    assert "规则 [temp <= 55] 剔除" in report2       # 第 8 节逐条留痕
    assert "规则 [temp <= 55]" not in report_text    # 默认配置里没有这条规则


# ------------------------------------------------------------------ 判定矩阵
def _evidence(pep8_score=95.0, complete=True, repro=True, usage=True,
              replay=True, custom=3, bench_pass=True):
    return {
        "pep8": {"score": pep8_score, "passed": 190, "total": 200},
        "steps": core.EXPECTED_AUDIT_STEPS, "pipeline_complete": complete,
        "reproducible": {"log_reproducible": repro, "steps": 8},
        "usage": {"found": usage, "ref": "README.md:1", "code": ""},
        "replay": {"csv_identical": replay, "new_rows": 0, "clean_rows": 10},
        "custom_rules": {"count": custom, "removed": 0},
        "bench": None if bench_pass is None else
        {"rows": 1000000, "budget": 300.0, "pass": bench_pass},
    }


def test_workorder_tiers_pure_matrix():
    """workorder_tiers 判定矩阵：每个子条件缺失都精确拉掉对应档、不误伤。"""
    settings = load_config(RULES_PATH)
    ok = core.workorder_tiers(core.gate(95.0, settings), settings, _evidence())
    assert ok["tier_D_pass"] and ok["tier_C_good"]
    assert ok["tier_B_excellent"] and ok["tier_A_super"]
    mid = core.workorder_tiers(core.gate(89.0, settings), settings,
                               _evidence())     # 过 D/C 线，不过 B 线 90
    assert mid["tier_D_pass"] and mid["tier_C_good"]
    assert mid["tier_B_excellent"] is False and mid["tier_A_super"] is False
    no_repro = core.workorder_tiers(core.gate(95.0, settings), settings,
                                    _evidence(repro=False))
    assert no_repro["tier_C_good"] is False
    assert no_repro["tier_D_pass"] is True
    no_usage = core.workorder_tiers(core.gate(95.0, settings), settings,
                                    _evidence(usage=False))
    assert no_usage["tier_B_excellent"] is False
    assert no_usage["tier_C_good"] is True
    no_replay = core.workorder_tiers(core.gate(95.0, settings), settings,
                                     _evidence(replay=False))
    assert no_replay["tier_B_excellent"] is True
    assert no_replay["tier_A_super"] is False
    no_bench = core.workorder_tiers(core.gate(95.0, settings), settings,
                                    _evidence(bench_pass=None))
    assert no_bench["tier_A_super"] is False
    assert no_bench["bench_measured"] is False
    leaky = core.workorder_tiers(core.gate(95.0, settings), settings,
                                 _evidence(custom=0))
    assert leaky["tier_A_super"] is False       # 无自定义规则则 A 行不成立
    sloppy = core.workorder_tiers(core.gate(95.0, settings), settings,
                                  _evidence(pep8_score=80.0))
    assert sloppy["tier_D_pass"] is True        # 80 ≥ D 线 75
    assert sloppy["tier_B_excellent"] is False  # 80 < B 线 85
    broken_pipe = core.workorder_tiers(core.gate(95.0, settings), settings,
                                       _evidence(complete=False))
    assert broken_pipe["tier_D_pass"] is False
