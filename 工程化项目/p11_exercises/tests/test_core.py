# -*- coding: utf-8 -*-
import pytest

from exercise_five import core


def test_c_to_f_freezing_and_boiling():
    assert core.c_to_f(0) == 32.0 and core.c_to_f(100) == 212.0


def test_kpa_to_mpa():
    assert core.kpa_to_mpa(450.0) == 0.45


@pytest.mark.parametrize("a,b,c,exp", [(1, -3, 2, [2.0, 1.0]), (1, 2, 1, [-1.0])])
def test_quad_real_roots(a, b, c, exp):
    assert core.quad(a, b, c) == exp


def test_quad_complex_marker():
    assert core.quad(1, 0, 1) == ["complex"]


def test_quad_zero_discriminant_double_root():
    assert core.quad(1, -2, 1) == [1.0]


def test_registry_crud():
    reg = core.Registry()
    reg.add(core.Device("D1", "泵"))
    assert reg.count() == 1 and reg.get("D1").name == "泵"
    assert reg.remove("D1") is not None and reg.count() == 0
    assert reg.remove("NOPE") is None


def test_plc_inherits_device_and_extends():
    p = core.PLC("P1", "PLC", 50)
    assert isinstance(p, core.Device) and p.scan_ms == 50 and p.code == "P1"


def test_safe_read_missing_file():
    assert core.safe_read("/no/such/file") == "FILE_NOT_FOUND"
