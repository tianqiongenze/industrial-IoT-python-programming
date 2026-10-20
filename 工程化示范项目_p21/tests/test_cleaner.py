# -*- coding: utf-8 -*-
"""pytest 单元测试（GB/T 15532 测试思维：正常/边界/异常）"""
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from cleaning.cleaner import (drop_duplicates, unify_time, fill_missing,   # noqa: E402
                              clip_outliers, quality_score, CleaningPipeline)


def make_df():
    return pd.DataFrame({
        "ts": ["2026-09-01 08:00:00", "2026-09-01 08:00:00", "bad-time",
               "2026-09-01 08:05:00", "2026-09-01 08:10:00"],
        "temp": [78.0, 78.0, 85.0, None, 150.0],
        "vib": [2.0, 2.0, 2.5, 2.2, 2.4],
        "shift": ["白班", "白班", "夜班", None, "中班"],
    })


def test_drop_duplicates():
    d, info = drop_duplicates(make_df())
    assert len(d) == 4 and info["removed"] == 1


def test_unify_time_flags_bad():
    d, info = unify_time(make_df())
    assert info["invalid"] == 1 and d["ts"].isna().sum() == 1


def test_fill_missing_median():
    d, _ = fill_missing(make_df(), {"temp": "median"})
    assert d["temp"].isna().sum() == 0


def test_clip_outliers_removes_150():
    d, info = clip_outliers(make_df(), "temp")
    assert 150.0 not in d["temp"].values and info["removed"] >= 1


def test_pipeline_smoke():
    rules = {"missing": {"temp": "median", "shift": "未知"}, "outlier": {"method": "iqr"}}
    pipe = CleaningPipeline(rules)
    out = pipe.run(make_df())
    score, _ = quality_score(out, {})
    assert score >= 60 and len(pipe.audit) == 4
