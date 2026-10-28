# -*- coding: utf-8 -*-
"""每题 pytest 用例覆盖实测：超优(A)"每题附测试用例"的证据来源。

做法（确定性、零依赖）：用标准库 ast 解析 tests/*.py，把每个
test_ 开头的命名测试函数按其源码中出现的"题号标记"归到对应题目；
一题至少要有 tests_per_question_min 条才算"每题附测试用例"。
标记表 = 工单五题的可测口径（核心函数名 + exerciseN + 题号字样）。
"""
import ast
import os

QUESTIONS = ("题1", "题2", "题3", "题4", "题5")

#: 题号 → 判定标记（测试函数源码中出现任一标记即归属该题）
MARKERS = {
    "题1": ("convert_temperature", "temperature_level", "exercise1", "题1"),
    "题2": ("solve_quadratic", "exercise2", "题2"),
    "题3": ("Registry", "normalize_id", "exercise3", "题3"),
    "题4": ("Device", "PLC", "exercise4", "题4"),
    "题5": ("safe_read", "exercise5", "题5"),
}


def collect_tests(tests_dir):
    """返回 {题号: ["文件名::测试函数名", ...]}（排序稳定，可复现）。"""
    found = {number: [] for number in QUESTIONS}
    if not os.path.isdir(tests_dir):
        return found
    for name in sorted(os.listdir(tests_dir)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(tests_dir, name)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            segment = ast.get_source_segment(text, node) or node.name
            for number in QUESTIONS:
                if any(marker in segment for marker in MARKERS[number]):
                    found[number].append("%s::%s" % (name, node.name))
    for names in found.values():
        names.sort()
    return found


def count_per_question(tests_dir):
    """返回 {题号: 条数}（A 层闸门直接消费的真实计数）。"""
    return {number: len(names)
            for number, names in collect_tests(tests_dir).items()}
