# -*- coding: utf-8 -*-
"""规则表驱动的 Pandas 清洗管道（纯函数，无 IO）。"""
import pandas as pd


def make_dirty(n=200, seed=7):
    """合成含脏数据的 CSV（用于课堂对比实验）。"""
    import numpy as np
    rng = np.random.RandomState(seed)
    df = pd.DataFrame({
        "ts": pd.date_range("2026-03-01", periods=n, freq="h"),
        "vib": rng.normal(4.0, 0.5, n).round(3),
        "temp": rng.normal(55, 3, n).round(1)})
    df.loc[rng.choice(n, 10, replace=False), "vib"] = np.nan
    df.loc[rng.choice(n, 4, replace=False), "temp"] = 135.0
    df.loc[rng.choice(n, 4, replace=False), "vib"] = -1.0
    return df


def clean(df, temp_max=120.0, vib_min=0.0, vib_max=15.0):
    """三段式：去重 → 剔缺失 → 剔越界（顺序固定，保证口径可复现）。"""
    return (df.drop_duplicates()
              .dropna(subset=["vib"])
              .query("vib >= @vib_min and vib <= @vib_max and temp <= @temp_max")
              .reset_index(drop=True))


def quality(df, temp_max=120.0, vib_min=0.0, vib_max=15.0):
    """质量分 = 完整率 × 合理率。"""
    if len(df) == 0:
        return 0.0
    complete = float(df["vib"].notna().mean())
    valid = float(((df["vib"].between(vib_min, vib_max)) & (df["temp"] <= temp_max)).mean())
    return round(complete * valid, 4)


def gate(score, target=0.85):
    """质量门禁：低于目标即失败。"""
    return score >= target
