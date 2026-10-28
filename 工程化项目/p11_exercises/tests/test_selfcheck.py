# -*- coding: utf-8 -*-
"""内置断言表自身的服务测试（断言表是"数据"，也要被测试）。

对应 docs/04 用例 TC-S01~TC-S04：断言表完整性 + 执行器真实反映失败。
"""
from exercise_five import selfcheck


def test_build_cases_covers_all_five_exercises(cfg, files):
    """断言表覆盖五题，且每题都含 B 层以上档。"""
    cases = selfcheck.build_cases(cfg, files)
    numbers = {case["number"] for case in cases}
    assert numbers == {"题1", "题2", "题3", "题4", "题5"}
    assert all(case["tier"] in selfcheck.TIER_ORDER for case in cases)


def test_run_cases_returns_machine_readable_results(cfg, files):
    """执行器输出结构固定：ok/detail 字段供报告直接消费。"""
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    assert results and all("ok" in item for item in results)
    assert all(item["detail"] == "" or not item["ok"] for item in results)


def test_summarise_marks_failure_detail(files, cfg):
    """异常注入档：把某条断言改为必失败，汇总必须标 FAIL 并记原因。"""
    cases = selfcheck.build_cases(cfg, files)
    broken = dict(cases[0])
    broken["fn"] = lambda: 1 / 0            # 触发 ZeroDivisionError
    results = selfcheck.run_cases(cases[:1] + [broken])
    summary = selfcheck.summarise(results)
    assert summary["题1"]["pass"] is False
    assert any("ZeroDivisionError" in text for text in summary["题1"]["failed"])


def test_summarise_boundary_count_matches_table(cfg, files):
    """计数口径：边界档总数=表中空输入/极值/异常条数。"""
    cases = selfcheck.build_cases(cfg, files)
    summary = selfcheck.summarise(selfcheck.run_cases(cases))
    for number, bucket in summary.items():
        expected = [c for c in cases if c["number"] == number
                    and c["kind"] in selfcheck.BOUNDARY_KINDS]
        assert bucket["boundary_total"] == len(expected)
        assert bucket["total"] == len([c for c in cases
                                       if c["number"] == number])


def test_tier_gate_reports_informational_items(files, cfg):
    """达标线含"ℹ 不代跑 pytest"的信息项，不计入 PASS/FAIL 判定。"""
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    summary = selfcheck.summarise(results)
    gates = selfcheck.tier_gate(results, summary, {"score": 100.0, "total": 1,
                                                  "passed": 1,
                                                  "naming_violations": 0,
                                                  "missing_docstrings": 0},
                                {"entries": 15, "verified_entries": 15,
                                 "explain": "题2", "seed": 7, "required": 10,
                                 "pass": True})
    notes_items = [g for g in gates["gates"] if g["ok"] is None]
    assert len(notes_items) == 1
