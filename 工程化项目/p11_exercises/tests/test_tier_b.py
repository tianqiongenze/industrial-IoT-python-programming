# -*- coding: utf-8 -*-
"""优秀(B) 档：工单 B 行「5题全对；PEP 8≥85%；结构清晰」。

验收方式：全部用出厂真实测量（内置断言表 + stylecheck 实测）跑
selfcheck.tier_gate()，逐条断言 B 档 5 个证据项为真且整档判定"达标"；
"结构清晰"另用 check_structure() 的真实计数锁定（四件套/一题一函数/
src docstring），线值改动只允许发生在 config/rules.yaml。
"""
from exercise_five import config, exercises, selfcheck, stylecheck

# 故意缺 src/tests 层、函数无 docstring 的"脏结构"根目录用的源码
DIRTY_SRC = '"""脏样例。"""\n\n\ndef exercise1():\n    return 1\n'


def test_tier_b_all_five_exercises_run(cfg, files):
    """五题全部可执行且返回统一结果契约。"""
    runs = [exercises.exercise1(cfg), exercises.exercise2(cfg),
            exercises.exercise3(cfg), exercises.exercise4(cfg),
            exercises.exercise5(cfg, files)]
    assert [run_["number"] for run_ in runs] == ["题1", "题2", "题3", "题4",
                                                 "题5"]
    assert all(run_["lines"] for run_ in runs)


def test_tier_b_all_selfcheck_cases_pass(cfg, files):
    """内置断言全表（B 层含以上所有档）100% 通过。"""
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    failed = [item for item in results if not item["ok"]]
    assert failed == [], failed
    summary = selfcheck.summarise(results)
    assert all(bucket["pass"] for bucket in summary.values())


def test_tier_b_plc_and_device_structure(cfg):
    """题4 结构清晰：基类只管状态，子类扩展扫描行为并覆盖 start()。"""
    run_ = exercises.exercise4(cfg)
    payload = run_["payload"]
    assert payload["plc"]["scan_ms"] == int(cfg.plc["scan_ms"])
    assert payload["base"]["status"] == "运行"          # 基类 start 后状态
    assert len(payload["scans"]) == int(cfg.plc["scan_rounds"])


def test_tier_b_naming_conventions_clean(project_root):
    """命名规范检查：snake_case/PascalCase 违规数为 0。"""
    result = stylecheck.summarize(project_root)
    assert result["naming_violations"] == 0


def test_tier_b_pep8_subset_at_least_85(project_root, cfg):
    """PEP 8 子集实测得分 ≥ 出厂 B 线（工单优秀行 85%，真实测量非估算）。"""
    result = stylecheck.summarize(project_root)
    assert cfg.pep8_pass_rate_b == 85.0
    assert result["score"] >= cfg.pep8_pass_rate_b


def test_tier_b_threshold_and_topk_come_from_config(cfg):
    """配置驱动：warn/danger/topk/删除键改变会真实改变结果。"""
    run1 = exercises.exercise1(cfg)
    run3 = exercises.exercise3(cfg)
    assert run1["payload"]["warn"] == cfg.warn
    assert run1["payload"]["danger"] == cfg.danger
    assert len(run3["payload"]["keys"]) == len(cfg.device_rows) - 1
    assert len(run3["payload"]["rows"]) == len(cfg.device_rows) - 1


def _full_notes_info(cfg):
    """B 档不消费笔记字段，但分层线需要一份真实快照（同 D/C 文件口径）。"""
    return {"verified_entries": 15, "required": 10, "pass": True,
            "explain": "题3", "seed": cfg.seed, "exists": True,
            "questions_covered": 5, "sections_complete": True}


def _b_gates(cfg, files, style):
    """真实断言表 + 指定规范度量 → 分层线，并顺带取出 B 档 5 个证据项。"""
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    summary = selfcheck.summarise(results)
    gates = selfcheck.tier_gate(results, summary, style,
                                _full_notes_info(cfg), cfg)
    items = [g for g in gates["gates"] if g["tier"] == "B"]
    return gates, items


def test_tier_b_shipped_lines_match_work_order(cfg):
    """出厂 B 档线来自 rules.yaml：优秀线 5 题、PEP 8 B 线 85%。"""
    assert cfg.b_min_correct == 5
    assert cfg.pep8_pass_rate_b == 85.0


def test_tier_b_gate_items_all_pass_on_real_run(cfg, files, project_root):
    """B 档 5 个证据项（五题全对/断言 B 子集/命名违规/PEP 8/结构）全 PASS。"""
    style = stylecheck.summarize(project_root)
    gates, items = _b_gates(cfg, files, style)
    assert len(items) == 5, items
    assert all(item["ok"] is True for item in items), items
    assert gates["tier_pass"]["B"] is True
    assert gates["tiers"]["B"]["verdict"] == "达标"


def test_tier_b_structure_metrics_are_measured(project_root):
    """结构清晰是"真计数"：四件套 4/4、一题一函数 5/5 全含 docstring、
    src 模块 docstring 全覆盖（分母 >0，不是空表通过）。"""
    structure = stylecheck.check_structure(project_root)
    assert structure["parts_total"] == 4
    assert structure["parts_present"] == 4
    assert structure["exercise_functions"] == 5
    assert structure["exercise_functions_documented"] == 5
    assert structure["src_modules_total"] >= 11
    assert (structure["src_modules_documented"]
            == structure["src_modules_total"])


def test_tier_b_structure_gate_fails_on_dirty_layout(cfg, files, tmp_path):
    """可证伪：只有 src 一层、exercise1 无 docstring 时，"结构清晰"项判 FAIL。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "exercises.py").write_text(DIRTY_SRC,
                                                   encoding="utf-8")
    structure = stylecheck.check_structure(str(tmp_path))
    assert structure["parts_present"] == 1
    assert structure["exercise_functions"] == 1
    assert structure["exercise_functions_documented"] == 0
    style = dict(stylecheck.check_paths([]), structure=structure)
    style["score"] = 100.0
    gates, items = _b_gates(cfg, files, style)
    structure_item = [g for g in items if "结构清晰" in g["item"]]
    assert len(structure_item) == 1
    assert structure_item[0]["ok"] is False
    assert "工程四件套 1/4" in structure_item[0]["item"]
    assert gates["tier_pass"]["B"] is False


def test_tier_b_pep8_line_is_config_only(cfg, files, tmp_path):
    """改配置不改代码：同一实测 86.0%，B 线 85 判过、抬到 90 判不过。"""
    style = dict(stylecheck.check_paths([]), score=86.0, passed=43, total=50)
    gates, items = _b_gates(cfg, files, style)
    band = [g for g in items if "PEP 8" in g["item"]][0]
    assert band["ok"] is True and "≥ B 层线 85.0%" in band["item"]
    path = tmp_path / "b_line.yaml"
    path.write_text("warn: 60.0\ndanger: 90.0\npep8_pass_rate_d: 75.0\n"
                    "pep8_pass_rate_b: 90.0\n", encoding="utf-8")
    strict = config.load_config(str(path))
    assert strict.pep8_pass_rate_b == 90.0
    gates2, items2 = _b_gates(strict, files, style)
    band2 = [g for g in items2 if "PEP 8" in g["item"]][0]
    assert band2["ok"] is False
    assert gates2["tier_pass"]["B"] is False


def test_tier_b_five_questions_gate_fails_at_four(cfg, files, project_root):
    """可证伪：题5 断言全破时"五题全对"项 FAIL，且正确数降为 4（<优秀线）。"""
    cases = selfcheck.build_cases(cfg, files)
    broken = [dict(case, fn=(lambda: False)) if case["number"] == "题5"
              else case for case in cases]
    results = selfcheck.run_cases(broken)
    summary = selfcheck.summarise(results)
    style = stylecheck.summarize(project_root)
    gates = selfcheck.tier_gate(results, summary, style,
                                _full_notes_info(cfg), cfg)
    five = [g for g in gates["gates"]
            if g["tier"] == "B" and "题1-5" in g["item"]][0]
    assert five["ok"] is False
    assert "正确 4/5" in five["item"]
    assert gates["tier_pass"]["B"] is False


def test_tier_b_summary_line_carries_real_numbers(cfg, files, project_root):
    """优秀(B) 汇总行：题数、PEP 8 达标率与分母、结构三组计数全部印真实数字。"""
    style = stylecheck.summarize(project_root)
    gates, _items = _b_gates(cfg, files, style)
    text = gates["tiers"]["B"]["summary"]
    structure = style["structure"]
    assert "B 层 优秀" in text and "5题全对" in text
    assert "正确 5/5" in text and "达标率 %.1f%%" % style["score"] in text
    assert "检查项通过 %d/%d" % (style["passed"], style["total"]) in text
    assert "四件套 %d/%d" % (structure["parts_present"],
                            structure["parts_total"]) in text
    assert "一题一函数 %d/5" % structure["exercise_functions"] in text
    src_docstring = "src 模块 docstring %d/%d" % (
        structure["src_modules_documented"], structure["src_modules_total"])
    assert src_docstring in text
    assert gates["tiers"]["B"]["verdict"] == "达标"
