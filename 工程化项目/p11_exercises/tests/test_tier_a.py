# -*- coding: utf-8 -*-
"""超优(A) 档：工单 A 行「优秀+每题附测试用例与《迁移笔记》」。

验收口径全部是真实测量：
  · 每题附测试用例 = testmap 用标准库 ast 扫 tests/ 得到的每题命名
    用例真实计数（线值 = rules.yaml 的 tests_per_question_min）；
  · 《迁移笔记》= docs/09 文件真实存在 + notes.audit() 实测条数、
    逐题常见错误覆盖 5/5、P1.2 布局映射等必备章节齐全；
  · A 档第一条证据就是"优秀(B) 层达标"（超优 = 优秀 + 附加项），
    因此 B 档破 → A 档必破（本文件锁定该依赖链）。
"""
import os

from exercise_five import (config, notes, selfcheck, stylecheck, testmap)


def _full_style(project_root):
    """出厂真实规范度量（含 testmap 每题用例计数，与 pipeline 同源）。"""
    style = stylecheck.summarize(project_root)
    style["question_tests"] = testmap.count_per_question(
        os.path.join(project_root, "tests"))
    return style


def _full_notes_info(cfg, style=None):
    """笔记实测快照：由 notes.write() 真渲染真审计得到，不手写数字。"""
    _text, info = notes.write(cfg, style or {"score": 100.0, "total": 1,
                                             "passed": 1},
                              "docs/09-C转Python迁移笔记.md")
    info["exists"] = True
    return info


def _a_items(gates):
    return [g for g in gates["gates"] if g["tier"] == "A"]


def test_tier_a_every_exercise_has_three_boundary_kinds(cfg, files):
    """断言表结构：每题都齐 空输入 / 极值 / 异常 三档且各 ≥3 条。"""
    cases = selfcheck.build_cases(cfg, files)
    for number in ("题1", "题2", "题3", "题4", "题5"):
        kinds = [case["kind"] for case in cases if case["number"] == number]
        for kind in selfcheck.BOUNDARY_KINDS:
            assert kinds.count(kind) >= 1, (number, kind)
        boundary = [k for k in kinds if k in selfcheck.BOUNDARY_KINDS]
        assert len(boundary) >= 3, (number, boundary)


def test_tier_a_all_boundary_assertions_pass(cfg, files):
    """A 层边界断言全部为真（不是"写了但没跑"）。"""
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    summary = selfcheck.summarise(results)
    assert all(bucket["boundary_enough"] for bucket in summary.values())
    boundary_failed = [item for item in results
                       if item["kind"] in selfcheck.BOUNDARY_KINDS
                       and not item["ok"]]
    assert boundary_failed == [], boundary_failed


def test_tier_a_gate_is_green(cfg, files, project_root):
    """A 档可自动判定项全 PASS：优秀依赖链 + 每题用例 + 边界 + 笔记。"""
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    summary = selfcheck.summarise(results)
    gates = selfcheck.tier_gate(results, summary, _full_style(project_root),
                                _full_notes_info(cfg), cfg)
    assert gates["tier_pass"]["A"] is True
    items = _a_items(gates)
    assert all(g["ok"] or g["ok"] is None for g in items), items
    assert gates["tiers"]["A"]["verdict"] == "达标"


def test_tier_a_requires_b_tier_pass(cfg, files, project_root):
    """依赖链：PEP 8 实测 80%（B 线 85 不过）→ B 破 → A 的"优秀层达标"项破。"""
    style = _full_style(project_root)
    style["score"] = 80.0
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    summary = selfcheck.summarise(results)
    gates = selfcheck.tier_gate(results, summary, style,
                                _full_notes_info(cfg, style), cfg)
    assert gates["tier_pass"]["B"] is False
    chain = [g for g in _a_items(gates) if "优秀(B)层达标" in g["item"]]
    assert len(chain) == 1 and chain[0]["ok"] is False
    assert gates["tier_pass"]["A"] is False
    # 及格(D) 只要求 75% 线，故仍达标：证明档位依赖不是"一起 False"
    assert gates["tier_pass"]["D"] is True


def test_tier_a_question_test_counts_are_real(project_root):
    """每题附测试用例=真计数：五题各自 ≥1 条，且总数等于 tests/ 用例和。"""
    counts = testmap.count_per_question(
        os.path.join(project_root, "tests"))
    assert set(counts) == set(testmap.QUESTIONS)
    assert all(count >= 1 for count in counts.values()), counts
    collected = testmap.collect_tests(os.path.join(project_root, "tests"))
    assert sum(counts.values()) == sum(len(names) for names in
                                       collected.values())
    listing = [item for number in testmap.QUESTIONS
               for item in collected[number]]
    assert all("::test_" in item for item in listing), listing[:5]


def test_tier_a_question_line_is_config_only(cfg, files, project_root,
                                             tmp_path):
    """改配置不改代码：每题用例线抬到 999 → A 档"每题附测试用例"判不过。"""
    style = _full_style(project_root)
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    summary = selfcheck.summarise(results)
    base = selfcheck.tier_gate(results, summary, style,
                               _full_notes_info(cfg, style), cfg)
    line_item = [g for g in _a_items(base) if "每题附测试用例" in g["item"]][0]
    assert line_item["ok"] is True
    path = tmp_path / "tests_line.yaml"
    path.write_text("warn: 60.0\ndanger: 90.0\n"
                    "tests_per_question_min: 999\n", encoding="utf-8")
    strict = config.load_config(str(path))
    gates = selfcheck.tier_gate(results, summary, style,
                                _full_notes_info(strict, style), strict)
    item = [g for g in _a_items(gates) if "每题附测试用例" in g["item"]][0]
    assert item["ok"] is False
    assert "每题线 ≥999" in item["item"], item["item"]
    assert gates["tier_pass"]["A"] is False


def test_tier_a_notes_gate_fails_when_notes_missing(cfg, files, project_root):
    """可证伪：笔记不存在（--no-notes 场景）→ A 档笔记项与整档判不过。"""
    style = _full_style(project_root)
    info = _full_notes_info(cfg, style)
    info["exists"] = False
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    summary = selfcheck.summarise(results)
    gates = selfcheck.tier_gate(results, summary, style, info, cfg)
    notes_item = [g for g in _a_items(gates) if "迁移笔记" in g["item"]][0]
    assert notes_item["ok"] is False
    assert "文件存在=否" in notes_item["item"]
    assert gates["tier_pass"]["A"] is False


def test_tier_a_notes_audit_is_complete(cfg, files):
    """笔记完整性实测：渲染文本审计出逐题 5/5 + 必备章节齐全 + 条数达标。"""
    style = {"score": 100.0, "total": 1, "passed": 1}
    text, info = notes.write(cfg, style, "docs/09-C转Python迁移笔记.md")
    audit = notes.audit(text)
    assert audit["questions_covered"] == 5, audit
    assert audit["sections_found"] == audit["sections_total"] == 2
    assert audit["sections_complete"] is True
    assert audit["entries"] >= notes.ENTRY_COUNT_REQUIRED
    assert info["questions_covered"] == 5
    assert info["sections_complete"] is True
    assert info["complete"] is True


def test_tier_a_migration_notes_generated_and_long_enough(cfg, project_root):
    """迁移笔记是项目生成的真实交付物，实测条目 ≥10。"""
    style = _full_style(project_root)
    text, stats = notes.write(cfg, style, "docs/09-C转Python迁移笔记.md")
    assert stats["verified_entries"] >= notes.ENTRY_COUNT_REQUIRED
    assert stats["entries"] == stats["verified_entries"]
    for keyword in ("引用语义", "决策矩阵", "safe_read", "Registry",
                    "convert_temperature", "solve_quadratic"):
        assert keyword in text, keyword


def test_tier_a_notes_file_exists_on_disk(project_root):
    """跑过 run.py 后 docs/09 文件必须真实存在（文档↔代码不脱节）。"""
    path = os.path.join(project_root, "docs", "09-C转Python迁移笔记.md")
    assert os.path.exists(path), "请先执行 python run.py 生成迁移笔记"
    text = open(path, encoding="utf-8").read()
    assert notes.count_entries(text) >= notes.ENTRY_COUNT_REQUIRED
    audit = notes.audit(text)
    assert audit["questions_covered"] == 5
    assert audit["sections_complete"] is True


def test_tier_a_explain_pick_is_deterministic(cfg):
    """讲解抽签：同一 seed 必须每次抽到同一题（可复现）。"""
    first = notes._explain_pick(cfg.seed)
    second = notes._explain_pick(cfg.seed)
    assert first == second and first in ("题1", "题2", "题3", "题4", "题5")


def test_tier_a_summary_line_carries_real_numbers(cfg, files, project_root):
    """超优(A) 汇总行：每题 pytest 用例计数与笔记实测全部印真实数字。"""
    style = _full_style(project_root)
    results = selfcheck.run_cases(selfcheck.build_cases(cfg, files))
    summary = selfcheck.summarise(results)
    info = _full_notes_info(cfg, style)
    gates = selfcheck.tier_gate(results, summary, style, info, cfg)
    text = gates["tiers"]["A"]["summary"]
    counts = style["question_tests"]
    for number in testmap.QUESTIONS:
        assert "%s %d" % (number, counts[number]) in text, (number, text)
    assert "线 ≥%d" % cfg.tests_per_question_min in text
    assert "存在=是" in text
    assert "正文 %d 条" % info["verified_entries"] in text
    assert "逐题易错点 5/5" in text and "必备章节=是" in text
    assert gates["tiers"]["A"]["verdict"] == "达标"
