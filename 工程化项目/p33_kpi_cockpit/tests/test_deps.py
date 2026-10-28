# -*- coding: utf-8 -*-
"""依赖探测测试（审计项修复：原"特性探测"try 体里没有任何 import，永不降级）。

这里用「真的把包装坏 / 真的没装」两种情形，证明探测会真实切换模式，
且报告文案与实际路径一致（杜绝谎报）。
"""
import pytest

from kpi_cockpit import deps


def test_probe_stdlib_is_native():
    p = deps.probe("json")
    assert p.installed is True and p.mode == "native"


def test_probe_missing_module_is_fallback():
    p = deps.probe("definitely_not_installed_pkg_xyz")
    assert p.installed is False and p.mode == "fallback"
    assert p.version == ""


def test_probe_broken_package_reports_import_failure(tmp_path, monkeypatch):
    """包目录存在但 import 就抛 → 必须判为 fallback，而不是"存在即已安装"。"""
    pkg = tmp_path / "brokenpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("raise RuntimeError('坏包')\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    p = deps.probe("brokenpkg")
    assert p.installed is False and p.mode == "fallback"
    assert "import 失败" in p.why


def test_detect_covers_every_declared_optional():
    got = deps.detect()
    assert set(got) == set(deps.OPTIONAL)
    assert all(callable(v.as_dict) for v in got.values())


def test_summary_separates_native_and_fallback(monkeypatch):
    probes = {"streamlit": deps.Probe("streamlit", True, "1.65.0"),
              "plotly": deps.Probe("plotly", False, "")}
    s = deps.summary(probes)
    assert "已安装(原生启用): streamlit" in s
    assert "缺失(降级兜底): plotly" in s
    assert "1.65.0" not in s                      # 摘要只报模式，版本留给 result.json


def test_summary_handles_all_installed_and_all_missing():
    assert deps.summary({"a": deps.Probe("a", True, "1")}).endswith("缺失(降级兜底): 无")
    assert "已安装(原生启用): 无" in deps.summary({"a": deps.Probe("a", False, "")})


def test_probe_dict_shape_and_repr():
    p = deps.Probe("jinja2", True, "3.1.6", "模板引擎")
    assert p.as_dict() == {"name": "jinja2", "installed": True, "version": "3.1.6",
                           "mode": "native", "why": "模板引擎"}
    assert repr(p) == "Probe(jinja2=native)"


def test_probe_version_matches_importlib_metadata():
    """探测到的版本必须来自发行元数据，不许写死。"""
    import importlib.metadata as md
    assert deps.probe("jinja2").version == md.version("Jinja2")


def test_dist_name_maps_yaml_to_pyyaml():
    assert deps._dist_name("yaml") == "PyYAML"
    assert deps._dist_name("plotly") == "plotly"


def test_real_env_reality_check():
    """本机 pp03 环境的真实结论（写进报告的那句话必须与此一致）。"""
    got = deps.detect()
    assert got["streamlit"].installed and got["jinja2"].installed
    assert got["reportlab"].installed and got["pandas"].installed
