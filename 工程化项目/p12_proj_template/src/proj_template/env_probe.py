# -*- coding: utf-8 -*-
"""A 层规范闸门的**真实**环境探测：只回答"本机能否导入这个工具"，绝不执行工具。

课程解释器（/opt/anaconda3/envs/pp03/bin/python）离线、未安装 black/flake8/pylint，
因此本项目**不允许**在报告里写"已格式化/已通过 flake8"这类话。探测口径：
  probe("black") -> {"name","installed","version","declared_in_hook"}
  installed 只表示 importlib 能定位到该模块（find_spec），不代表已运行；
  version 取发行元数据，取不到则留空字符串。
一旦课堂机器装上 pre-commit + black + flake8，同一份代码即如实显示"本机可导入"，
生成项目里的 .pre-commit-config.yaml 会由 git 在 commit 前触发——本模块从不假装触发过。
"""
import importlib.metadata as md
import importlib.util

#: 规范闸门可能用到的工具：导入名 -> (发行名, 说明)
TOOLS = {
    "black": ("black", "代码格式化（pre-commit hook: black .）"),
    "flake8": ("flake8", "静态检查（pre-commit hook: flake8 src tests）"),
    "pylint": ("pylint", "评分检查（工单要求 --fail-under=8.5）"),
    "ruff": ("ruff", "一体化检查（可选替代 flake8）"),
    "pre_commit": ("pre-commit", "钩子安装器（pre-commit install）"),
    "pytest": ("pytest", "测试运行器（生成骨架的 tests/ 用得上）"),
}


def probe(name):
    """真实探测单个工具是否可导入；不 import 执行任何副作用，也不运行命令行工具。"""
    dist = TOOLS.get(name, (name, ""))[0]
    installed = False
    version = ""
    try:
        installed = importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        installed = False
    if installed:
        try:
            version = md.version(dist)
        except Exception:
            version = ""
    return {"name": name, "installed": bool(installed), "version": version,
            "desc": TOOLS.get(name, (name, ""))[1]}


def detect(names=None):
    """按名字排序返回探测结果列表（顺序固定，保证报告逐字节可复现）。"""
    return [probe(n) for n in sorted(names if names is not None else TOOLS)]


def usable_names(items):
    return sorted(x["name"] for x in items if x["installed"])


def missing_names(items):
    return sorted(x["name"] for x in items if not x["installed"])


def summary(items):
    """一行式摘要：可导入 x/y ｜ 缺失 y-x/y（缺失=本机跑不了，报告如实标注）。"""
    ok = usable_names(items)
    return "本机可导入 %d/%d：%s ｜ 缺失 %d 个：%s" % (
        len(ok), len(items), ", ".join(ok) or "无",
        len(items) - len(ok), ", ".join(missing_names(items)) or "无")


def hook_coverage(items, hooks):
    """把钩子里声明的每个工具映射到本机可执行性（逐条，不合并、不含糊）。"""
    by = {x["name"]: x for x in items}
    lines = []
    for hook in hooks:
        p = by.get(hook)
        if p is None:
            p = probe(hook)
        lines.append("%s：钩子已声明=%s，本机可导入=%s%s"
                     % (hook, "是", "是" if p["installed"] else "否",
                        "（版本 %s）" % p["version"] if p["installed"] and p["version"] else ""))
    return lines


def report_lines(items, hooks):
    """A 层报告段文本：钩子声明 + 探测结论 + 诚实的执行状态声明（绝不谎报已运行）。"""
    lines = ["钩子声明 %d 个：%s" % (len(hooks), ", ".join(hooks) or "无")]
    lines += hook_coverage(items, hooks)
    lines.append(summary(items))
    tail = "工具齐备，pip 装 pre-commit 后即生效" if len(usable_names(items)) == len(items) \
        else "当前环境缺工具，装上后同一份钩子即真正拦截"
    lines.append("执行状态：本次运行未调用 black/flake8/pylint/pre-commit 任何命令；"
                 "钩子文件已生成，须 pre-commit install 后由 git 在 commit 前触发（%s）" % tail)
    return lines
