# -*- coding: utf-8 -*-
"""五步清洗管道（GB/T 8566 过程思维：每步一个函数、可测可审）"""
import pandas as pd


def drop_duplicates(df: pd.DataFrame):
    before = len(df)
    out = df.drop_duplicates()
    return out, {"step": "去重", "removed": before - len(out)}


def unify_time(df: pd.DataFrame, col: str = "ts"):
    out = df.copy()
    out[col] = pd.to_datetime(out[col], errors="coerce")
    bad = int(out[col].isna().sum())
    return out, {"step": "时间统一", "invalid": bad}


def fill_missing(df: pd.DataFrame, rules: dict):
    out = df.copy()
    notes = []
    for col, how in rules.items():
        if col not in out.columns:
            continue
        if how == "median":
            out[col] = out[col].fillna(out[col].median())
        elif how == "interpolate":
            out[col] = out[col].interpolate()
        else:
            out[col] = out[col].fillna(how)
        notes.append(f"{col}←{how}")
    return out, {"step": "缺失处理", "rules": ",".join(notes)}


def clip_outliers(df: pd.DataFrame, col: str = "temp", k: float = 1.5):
    q1, q3 = df[col].quantile([.25, .75])
    iqr = q3 - q1
    lo, hi = q1 - k * iqr, q3 + k * iqr
    mask = (df[col] >= lo) & (df[col] <= hi)
    removed = int((~mask).sum())
    return df[mask], {"step": "离群剔除", "removed": removed,
                      "bounds": [round(float(lo), 1), round(float(hi), 1)]}


def quality_score(df: pd.DataFrame, weights: dict):
    completeness = 1 - df[["temp", "vib"]].isna().any(axis=1).mean()
    validity = 1 - ((df["temp"] < 40) | (df["temp"] > 110)).mean()
    uniqueness = 1 - df.duplicated().mean()
    score = (weights.get("completeness", .4) * completeness
             + weights.get("validity", .4) * validity
             + weights.get("uniqueness", .2) * uniqueness) * 100
    return round(float(score), 1), {"完整性": round(completeness * 100, 1),
                                    "合规性": round(validity * 100, 1),
                                    "唯一性": round(uniqueness * 100, 1)}


class CleaningPipeline:
    """五步管道：步骤台账全程留痕（审计要求）"""

    def __init__(self, rules: dict):
        self.rules = rules
        self.audit = []

    def run(self, df: pd.DataFrame):
        log = []
        d, info = drop_duplicates(df)
        log.append(info)
        d, info = unify_time(d, self.rules.get("time_column", "ts"))
        log.append(info)
        d, info = fill_missing(d, self.rules.get("missing", {}))
        log.append(info)
        o = self.rules.get("outlier", {})
        d, info = clip_outliers(d, "temp", float(o.get("k", 1.5)))
        log.append(info)
        self.audit = log
        return d
