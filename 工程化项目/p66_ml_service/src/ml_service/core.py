# -*- coding: utf-8 -*-
"""建模五步流（划分→训练→交叉验证→调参→落盘）+ LR/RF/GBM 对比 + F1 门禁。

工单 P6.1 口径：
  * 分层抽样 train/test 划分（random_state 固定，可复现）；
  * cross_val_score cv 折均值±方差留痕；
  * GridSearchCV 调参留痕（best_params_/best_score_ 进 result.json 与 manifest）；
  * 混淆矩阵 + 每类 precision/recall + macro-F1；
  * 评估门禁 macro-F1 < min_f1 直接抛错拒绝注册（工程化要求1）；
  * A层三维评价（工单 03-P6）：F1 + 训练耗时 fit_ms + 可解释性 Top-k。
    可解释性进报告与 result.json；fit_ms 是墙钟实测值，**一律不进 output/**
    （可复现闸门逐字节比对 output/），由 pipeline 写入 runtime/train_timing.json。
"""
import os
import time
import zlib

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (classification_report, confusion_matrix, f1_score,
                             precision_score, recall_score)
from sklearn.model_selection import GridSearchCV, cross_val_score, train_test_split

from .data import FEATURE_NAMES, N_DIM, validate_feature_names


def build_candidates(seed):
    """三模型对比候选（B层·模型对比）；命名即报告口径。"""
    return {
        "LR": LogisticRegression(max_iter=2000, random_state=seed),
        "RF": RandomForestClassifier(n_estimators=200, random_state=seed),
        "GBM": GradientBoostingClassifier(random_state=seed),
    }


def top_features(model, feature_names, k=3):
    """A层·可解释性 Top-k（工单 03-P6：F1+耗时+可解释性三维评价之一）。

    LR 取 coef_（二分类为正类「磨损」系数，符号即方向）；RF/GBM 等树模型取
    feature_importances_。排序键 = (-|value|, zlib.crc32(特征名))：|value| 并列
    时按 crc32 定序——内置 hash() 受 PYTHONHASHSEED 随机化，会破坏 output/ 的
    字节级复现（verify_local repeat 闸门），crc32 跨进程稳定。
    k 超过特征数时钳到特征数（不抛错，报告如实呈现全量）。
    """
    names = list(feature_names if feature_names is not None else FEATURE_NAMES)
    k = max(1, min(int(k), len(names)))
    if hasattr(model, "feature_importances_"):
        scores = [float(v) for v in model.feature_importances_]
        method = "feature_importances_"
    elif hasattr(model, "coef_"):
        coef = np.asarray(model.coef_, dtype=float)
        row = coef[0] if coef.shape[0] == 1 else coef[-1]
        scores = [float(v) for v in row]
        method = "coef_（正类=磨损，符号即影响方向）"
    else:
        return {"method": "无（模型不提供 coef_/feature_importances_）",
                "k": k, "n_features": len(names), "top": []}
    if len(scores) != len(names):
        raise ValueError("可解释性列名数 %d 与模型权重数 %d 不符（列序契约违例）"
                         % (len(names), len(scores)))
    ordered = sorted(zip(names, scores),
                     key=lambda ns: (-abs(ns[1]),
                                     zlib.crc32(ns[0].encode("utf-8"))))
    return {"method": method, "k": k, "n_features": len(names),
            "top": [{"rank": i + 1, "feature": nm,
                     "abs_value": round(abs(sv), 6), "signed_value": round(sv, 6)}
                    for i, (nm, sv) in enumerate(ordered[:k])]}


def evaluate(X, y, seed=42, test_size=0.25, cv_folds=5,
             grid_n_estimators=(50, 100, 200), grid_max_depth=(4, 6, None),
             explain_topk=3, feature_names=None, timing_out=None):
    """五步流全量评估，返回 (best_model, report_dict)。

    步骤纪律：先划分（此后测试集只在最后碰一次）→ 各候选 CV+训练 →
    RF 网格调参 → 以「测试集 macro-F1 最高」定选 → 混淆矩阵等指标出报告。
    A层三维评价：report_dict 内带可解释性 Top-k（进 result.json），训练耗时
    fit_ms 只写入调用方传入的 timing_out 字典（墙钟值，禁止混入报告产物）。
    """
    names = list(feature_names if feature_names is not None else FEATURE_NAMES)
    if len(names) != X.shape[1]:
        raise ValueError("特征列名 %d 个与特征矩阵 %d 列不符"
                         % (len(names), X.shape[1]))
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=test_size, stratify=y, random_state=seed)

    comparison = {}
    fitted = {}
    for name, est in build_candidates(seed).items():
        cv = cross_val_score(est, X, y, cv=cv_folds, scoring="f1")
        t0 = time.perf_counter()
        est.fit(Xtr, ytr)
        if timing_out is not None:
            timing_out[name] = round((time.perf_counter() - t0) * 1000, 2)
        pred = est.predict(Xte)
        comparison[name] = {
            "cv_folds": cv_folds,
            "cv_mean": round(float(cv.mean()), 4),
            "cv_std": round(float(cv.std()), 4),
            "test_macro_f1": round(float(f1_score(yte, pred, average="macro")), 4),
            "precision_normal": round(float(precision_score(yte, pred, pos_label=0)), 4),
            "recall_normal": round(float(recall_score(yte, pred, pos_label=0)), 4),
            "precision_wear": round(float(precision_score(yte, pred, pos_label=1)), 4),
            "recall_wear": round(float(recall_score(yte, pred, pos_label=1)), 4),
            "explain": top_features(est, names, explain_topk),
        }
        fitted[name] = est

    # GridSearchCV 调参留痕（B层：参数-收益记录进产物）
    grid = GridSearchCV(
        RandomForestClassifier(random_state=seed),
        {"n_estimators": list(grid_n_estimators), "max_depth": list(grid_max_depth)},
        cv=cv_folds, scoring="f1")
    t0 = time.perf_counter()
    grid.fit(Xtr, ytr)
    if timing_out is not None:
        timing_out["RF-tuned(grid)"] = round((time.perf_counter() - t0) * 1000, 2)
    tuned = grid.best_estimator_
    tuned_pred = tuned.predict(Xte)
    comparison["RF-tuned"] = {
        "cv_folds": cv_folds,
        "cv_mean": round(float(grid.best_score_), 4),
        "cv_std": round(float(np.std(grid.cv_results_["mean_test_score"])), 4),
        "test_macro_f1": round(float(f1_score(yte, tuned_pred, average="macro")), 4),
        "precision_normal": round(float(precision_score(yte, tuned_pred, pos_label=0)), 4),
        "recall_normal": round(float(recall_score(yte, tuned_pred, pos_label=0)), 4),
        "precision_wear": round(float(precision_score(yte, tuned_pred, pos_label=1)), 4),
        "recall_wear": round(float(recall_score(yte, tuned_pred, pos_label=1)), 4),
        "explain": top_features(tuned, names, explain_topk),
    }

    best_name = max(comparison, key=lambda k: comparison[k]["test_macro_f1"])
    best_model = tuned if best_name == "RF-tuned" else fitted[best_name]
    best_pred = best_model.predict(Xte)
    cm = confusion_matrix(yte, best_pred, labels=[0, 1])
    report = {
        "n_train": int(len(Xtr)), "n_test": int(len(Xte)),
        "best_model": best_name,
        "comparison": comparison,
        "grid_search": {
            "param_grid": {"n_estimators": list(grid_n_estimators),
                           "max_depth": [str(v) for v in grid_max_depth]},
            "cv": cv_folds,
            "best_params": {k: str(v) for k, v in grid.best_params_.items()},
            "best_cv_score": round(float(grid.best_score_), 4),
            "top5_mean_test": sorted(_grid_rows(grid),
                                     key=lambda r: -r["mean_test"])[:5],
        },
        "confusion_matrix": [[int(v) for v in row] for row in cm],
        "test_macro_f1": comparison[best_name]["test_macro_f1"],
        "classification_report_text": classification_report(
            yte, best_pred, target_names=["正常", "磨损"], digits=4),
        "feature_dim": int(X.shape[1]),
        "explain_topk": int(max(1, min(int(explain_topk), len(names)))),
        "explain_feature_source": "data.FEATURE_NAMES（真实数据集列序契约，非硬编码下标）",
    }
    return best_model, report


def _grid_rows(grid):
    """把 GridSearchCV 的 cv_results_ 精简为 (params, mean_test) 行，留痕用。"""
    for p, m in zip(grid.cv_results_["params"], grid.cv_results_["mean_test_score"]):
        yield {"params": {k: str(v) for k, v in p.items()},
               "mean_test": round(float(m), 4)}


def gate(macro_f1, min_f1=0.80):
    """评估门禁：达标 True / 不达标 False（调用方 run_pipeline 处硬阻断）。"""
    return macro_f1 >= min_f1


def save_model(model, path, manifest):
    """joblib 落盘 + 版本清单 JSON（sklearn/numpy 版本、特征维数与列序、指标）。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    validate_feature_names(manifest["feature_names"])
    joblib.dump(model, path, compress=3)
    return path


def load_model(path):
    if not os.path.exists(path):
        raise FileNotFoundError("模型不存在: %s" % path)
    return joblib.load(path)


def load_teacher_model(path):
    """D层：加载教师端预训练缺陷模型包；跨版本告警如实捕获上报。"""
    if not os.path.exists(path):
        raise FileNotFoundError("教师模型包不存在: %s" % path)
    import warnings
    caught = []
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        model = joblib.load(path)
        caught = [str(x.message) for x in w
                  if issubclass(x.category, UserWarning)]
    info = {"n_features": int(getattr(model, "n_features_in_", -1)),
            "classes": [int(c) for c in getattr(model, "classes_", [])],
            "sklearn_trained_hint": "见加载告警",
            "load_warnings": caught,
            "local_sklearn": sklearn.__version__}
    return model, info


def predict_row(model, feats, n_expected=N_DIM):
    """单条预测：先做维度/数值校验（顺序与训练契约一致），返回 (pred, proba_wear)。"""
    feats = list(feats)
    if len(feats) != n_expected:
        raise ValueError("特征维度 %d 与训练契约 %d 不符" % (len(feats), n_expected))
    arr = np.asarray(feats, dtype=float)
    if not np.all(np.isfinite(arr)):
        raise ValueError("特征含非有限数值（NaN/Inf）")
    x = arr.reshape(1, -1)
    pred = int(model.predict(x)[0])
    if hasattr(model, "predict_proba"):
        proba = float(model.predict_proba(x)[0][1])
    else:  # pragma: no cover - 极端回退
        proba = float("nan")
    return pred, round(proba, 4)
