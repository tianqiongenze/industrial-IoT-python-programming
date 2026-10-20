# -*- coding: utf-8 -*-
import pytest

from collector_hub import core


def test_restore_divides_by_scale():
    assert core.restore([250, 300], 10) == [25.0, 30.0]


@pytest.mark.parametrize("s", [0, -1])
def test_restore_rejects_non_positive_scale(s):
    with pytest.raises(ValueError):
        core.restore([1], s)


def test_reconcile_true_when_sum_matches():
    ok, diff = core.reconcile([[1.0, 2.0], [3.0]], [1.0, 2.0, 3.0])
    assert ok and diff == 0.0


def test_reconcile_false_when_sum_differs():
    ok, diff = core.reconcile([[1.0, 2.0]], [1.0, 2.0, 9.0])
    assert not ok and abs(diff + 9.0) < 1e-9


def test_sleep_with_exponential():
    assert core.sleep_with(0.01, 0) == 0.01
    assert core.sleep_with(0.01, 3) == 0.08


def test_read_uses_injected_transport():
    src = {"id": "P", "n": 3}
    out = core.read(lambda s: 250, src)
    assert out == [250, 250, 250]
