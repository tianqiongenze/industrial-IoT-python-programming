# -*- coding: utf-8 -*-
from pd_clean import core


def test_clean_reduces_rows_and_removes_bad():
    df = core.make_dirty(n=200, seed=7)
    c = core.clean(df.copy())
    assert len(c) < len(df)
    assert c["vib"].min() >= 0.0 and c["temp"].max() <= 120.0


def test_clean_is_deduped():
    import pandas as pd
    df = pd.DataFrame({"vib": [1.0, 1.0], "temp": [10.0, 10.0]})
    assert len(core.clean(df)) == 1


def test_quality_between_0_and_1():
    df = core.make_dirty(200, 7)
    c = core.clean(df.copy())
    q = core.quality(c)
    assert 0.0 <= q <= 1.0 and q > 0.8


def test_gate_true_when_above_target():
    assert core.gate(0.9, 0.85) is True


def test_gate_false_when_below_target():
    assert core.gate(0.5, 0.85) is False


def test_empty_frame_quality_zero():
    import pandas as pd
    assert core.quality(pd.DataFrame({"vib": [], "temp": []})) == 0.0
