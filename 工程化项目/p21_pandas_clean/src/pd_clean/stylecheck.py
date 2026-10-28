# -*- coding: utf-8 -*-
"""代码规范度量：真实测量，绝不编造分数。

口径与兄弟项目 p11_exercises 的 stylecheck **同一份内置子集标准**（同一规则集、
同一分母口径），避免两个项目各造一把尺子。两层能力：
  1. probe()   —— 探测环境里是否真的装了 pylint / flake8 / black /
                  pre-commit（用 subprocess 取版本号，装了才算可用）。
  2. check_paths() —— 环境没装时，用标准库 tokenize+ast 跑一份
                  **PEP 8 子集自检**，输出真实通过项/检查项与百分比，
                  报告里明确标注"内置子集，非 pylint 评分"。
工单 P2.1 的 D 层线（≥75%）与 B 层线（≥85%）从 config/rules.yaml 读取，
达标率数值本身全部由本模块实测得出。
"""
import ast
import io
import os
import re
import subprocess
import sys

MAX_LINE_LENGTH = 79
TOOLS = ("pylint", "flake8", "black", "pre-commit")
NAME_OK = re.compile(r"^_?[a-z][a-z0-9_]*$")
CONST_OK = re.compile(r"^_?[A-Z][A-Z0-9_]*$")
CLASS_OK = re.compile(r"^_?[A-Z][A-Za-z0-9]*$")


def probe_tool(name):
    """探测一个命令行工具；返回 {available, version, command, reason}。"""
    module = name.replace("-", "")
    argv = [sys.executable, "-m", module, "--version"]
    if name == "pre-commit":
        argv = [sys.executable, "-m", "pre_commit", "--version"]
    try:
        done = subprocess.run(argv, capture_output=True, text=True,
                              timeout=20, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "version": "", "command": " ".join(argv),
                "reason": "无法启动: %s" % exc}
    if done.returncode == 0:
        first = (done.stdout or done.stderr).strip().splitlines()
        return {"available": True, "version": first[0] if first else "",
                "command": " ".join(argv), "reason": ""}
    return {"available": False, "version": "", "command": " ".join(argv),
            "reason": "未安装（命令退出码 %d）" % done.returncode}


def probe(names=TOOLS):
    """按名单探测工具可用性（报告据此写"可用/不可用"）。"""
    return {name: probe_tool(name) for name in names}


def run_tool(name, args):
    """真实调用工具（仅当 probe 判定可用）；返回 (退出码, 文本)。"""
    result = subprocess.run([sys.executable, "-m",
                             name.replace("-", ""), *args],
                            capture_output=True, text=True, timeout=120,
                            check=False)
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def pylint_score(paths):
    """有 pylint 才出分：返回 {"available":..., "score":..., "output":...}。"""
    status = probe_tool("pylint")
    if not status["available"]:
        return {"available": False, "score": None,
                "note": status["reason"], "output": ""}
    code, text = run_tool("pylint", ["--score=y", *paths])
    match = re.search(r"rated at (-?\d+(?:\.\d+)?)/10", text)
    score = float(match.group(1)) if match else None
    return {"available": True, "score": score, "note": "pylint 实测评分",
            "exit_code": code, "output": text.strip()}


STAR_IMPORT = re.compile(r"\bimport\s+\*")


def _check_text(text):
    """对单个源文件跑 PEP 8 子集检查，返回 (违规清单, 检查项总数)。"""
    violations = []
    total = 0
    lines = text.splitlines()
    for number, line in enumerate(lines, 1):
        total += 1
        if line.rstrip() != line:
            violations.append(("W291", number, "行尾空格"))
        if "\t" in line[:len(line) - len(line.lstrip())]:
            violations.append(("E101", number, "缩进用了 Tab"))
        if len(line) > MAX_LINE_LENGTH:
            violations.append(("E501", number, "行长 %d>79" % len(line)))
    if text and not text.endswith("\n"):
        total += 1
        violations.append(("W292", len(lines), "文件末尾缺换行"))
    total += 1
    if STAR_IMPORT.search(text):
        violations.append(("F403", 0, "存在星号导入"))
    total += 1
    try:
        ast.parse(text)
    except SyntaxError as exc:
        violations.append(("E999", exc.lineno or 0, "语法错误: %s" % exc.msg))
    else:
        violations.extend(_check_names(text))
    return violations, total + _name_checks(text)


def _check_names(text):
    """命名规范：函数/变量 snake_case、类 PascalCase、模块常量大写。"""
    out = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not CLASS_OK.match(node.name):
            out.append(("C0103", node.lineno, "类名非 PascalCase: %s"
                        % node.name))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not NAME_OK.match(node.name):
                out.append(("C0103", node.lineno, "函数名非 snake_case: %s"
                            % node.name))
            # 与 pylint 默认 no-docstring-rgx=^_ 同口径：私有函数免检
            public = not node.name.startswith("_")
            if public and ast.get_docstring(node) is None:
                out.append(("C0116", node.lineno, "函数缺 docstring: %s"
                            % node.name))
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    if not CONST_OK.match(target.id):
                        out.append(("C0103", node.lineno,
                                    "常量命名异常: %s" % target.id))
    if ast.get_docstring(tree) is None:
        out.append(("C0114", 1, "模块缺 docstring"))
    return out


def _name_checks(text):
    """命名/文档检查项总数（与 _check_names 同一遍历口径）。"""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return 1
    count = 1                                   # 模块 docstring
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            count += 1
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # 私有函数（^_）与 pylint 同口径免 docstring 检查
            count += 1 if node.name.startswith("_") else 2
        if isinstance(node, ast.Assign):
            count += sum(1 for t in node.targets
                         if isinstance(t, ast.Name) and t.id.isupper())
    return count


def check_file(path):
    """单文件检查入口。"""
    with io.open(path, encoding="utf-8") as handle:
        return _check_text(handle.read())


def check_paths(paths):
    """扫描多个源文件：返回真实计数、百分比（保留一位）与逐文件得分明细。"""
    violations, total, files, per_file = [], 0, [], []
    for path in paths:
        if not os.path.isfile(path):
            continue
        files.append(path)
        with io.open(path, encoding="utf-8") as handle:
            found, count = _check_text(handle.read())
        label = os.path.basename(os.path.dirname(path)) + "/" + \
            os.path.basename(path)
        violations.extend((label, *item) for item in found)
        file_passed = count - len(found)
        per_file.append({"file": label, "total": count,
                         "passed": file_passed,
                         "score": round(file_passed * 100.0 / count, 1)
                         if count else 100.0})
        total += count
    passed = total - len(violations)
    score = round(passed * 100.0 / total, 1) if total else 100.0
    return {"checked_files": len(files), "total": total, "passed": passed,
            "violations": violations, "score": score, "per_file": per_file,
            "max_line_length": MAX_LINE_LENGTH}


def collect_sources(root):
    """收集项目源码文件（src/ + tests/ + run.py），供规范度量。"""
    found = []
    for sub in ("src", "tests"):
        base = os.path.join(root, sub)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            found.extend(os.path.join(dirpath, f) for f in filenames
                         if f.endswith(".py"))
    entry = os.path.join(root, "run.py")
    if os.path.isfile(entry):
        found.append(entry)
    return sorted(found)


def summarize(root):
    """给出"真实测量"摘要：内置子集分数 + 分类计数 + 违规明细前 N 条。"""
    result = check_paths(collect_sources(root))
    codes = [item[1] for item in result["violations"]]
    result["naming_violations"] = codes.count("C0103")
    result["missing_docstrings"] = codes.count("C0116") + codes.count("C0114")
    result["long_lines"] = codes.count("E501")
    result["top_violations"] = result["violations"][:10]
    return result
