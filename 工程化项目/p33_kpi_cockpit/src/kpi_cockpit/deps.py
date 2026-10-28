# -*- coding: utf-8 -*-
"""可选依赖真实探测（修复审计项：原 pipeline 的 try 体里没有 import，永不降级）。

用法约定（唯一真源）：
  probe("streamlit") -> Probe(name, installed, version, mode)
  mode 只有两种真实取值："native"（装了就当真用）与 "fallback"（没装走兜底路径），
  由 detect() 汇总后写入 report.txt / output/result.json，杜绝"谎报已安装"。
"""
import importlib
import importlib.metadata as md
import importlib.util

#: 本项目关心的可选依赖：包名 -> 说明（写进报告的降级提示）
OPTIONAL = {
    "streamlit": "Web 仪表盘（app.py 的运行时；缺失时以 AppTest 之外的 headless 路径自检）",
    "plotly": "交互图表（app.py 的 px.line / 良率仪表）",
    "jinja2": "日报 HTML 模板引擎（缺失时用内置 str 占位渲染）",
    "reportlab": "日报 PDF（缺失时只出 HTML，报告如实标注）",
    "pandas": "clean.csv 装载与附表（缺失时用 csv 标准库逐行装载）",
    "yaml": "rules.yaml 解析（缺失时用内置 yaml_lite）",
}


class Probe:
    """一个可选依赖的探测结果（不可变，便于报告直接引用）。"""

    __slots__ = ("name", "installed", "version", "why")

    def __init__(self, name, installed, version, why=""):
        self.name = name
        self.installed = bool(installed)
        self.version = version
        self.why = why

    @property
    def mode(self):
        return "native" if self.installed else "fallback"

    def __repr__(self):
        return "Probe(%s=%s)" % (self.name, self.mode)

    def as_dict(self):
        return {"name": self.name, "installed": self.installed,
                "version": self.version, "mode": self.mode, "why": self.why}


def probe(name):
    """真探测：find_spec 判存在，再取发行版本；不做任何 import 副作用假设。"""
    found = importlib.util.find_spec(name) is not None
    version = ""
    if found:
        try:
            importlib.import_module(name)          # 真 import，确认能加载而非仅存在
        except Exception as exc:                    # pragma: no cover - 坏包保护
            return Probe(name, False, "", "import 失败: %s" % exc)
        try:
            version = md.version(_dist_name(name))
        except Exception:
            version = getattr(importlib.import_module(name), "__version__", "")
    return Probe(name, found, version, OPTIONAL.get(name, ""))


def _dist_name(name):
    """导入名 -> 发行名（仅本项目用到的几个）。"""
    return {"yaml": "PyYAML", "reportlab": "reportlab"}.get(name, name)


def detect():
    """返回 {模块名: Probe}，供 pipeline/app 与报告统一取用。"""
    return {k: probe(k) for k in OPTIONAL}


def summary(probes):
    """人读一行式摘要：明确区分 native / fallback，绝不含糊。"""
    nat = [p.name for p in probes.values() if p.installed]
    fb = [p.name for p in probes.values() if not p.installed]
    return "已安装(原生启用): %s ｜ 缺失(降级兜底): %s" % (
        ", ".join(nat) or "无", ", ".join(fb) or "无")
