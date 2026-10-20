# -*- coding: utf-8 -*-

from proj_template import core


def test_file_templates_core_files_present():
    f = core.file_templates("proj", [])
    for k in ("README.md", ".gitignore", "src/__init__.py", "tests/__init__.py"):
        assert k in f


def test_file_templates_deps_written():
    f = core.file_templates("proj", ["numpy"])
    assert "numpy" in f["requirements.txt"]


def test_ensure_idempotent(tmp_path):
    f = core.file_templates("proj", ["pandas"])
    m1, k1 = core.ensure(str(tmp_path), f)
    m2, k2 = core.ensure(str(tmp_path), f)
    assert len(m1) == len(f) and not k1
    assert m2 == [] and len(k2) == len(f)


def test_verify_passes_after_ensure(tmp_path):
    f = core.file_templates("proj", ["pandas"])
    core.ensure(str(tmp_path), f)
    rep = core.verify(str(tmp_path), f)
    assert rep["missing"] == [] and rep["junk"] == []
