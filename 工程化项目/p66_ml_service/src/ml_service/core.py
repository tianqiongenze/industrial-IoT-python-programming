# -*- coding: utf-8 -*-
"""模型训练、评估门禁与推理（纯函数 + joblib 落盘）。"""
import os


def make_data(n=600, seed=42):
    """合成特征矩阵（5 维）与二分类标签。"""
    import numpy as np
    rng = np.random.RandomState(seed)
    X = rng.normal(0, 1, (n, 5))
    y = rng.binomial(1, 0.4, n)
    X[y == 1, :3] += 1.3
    return X, y


def train(X, y, test_size=0.25, seed=42):
    """训练随机森林并返回 (model, metrics)。"""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import f1_score
    from sklearn.model_selection import train_test_split
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=test_size, stratify=y, random_state=seed)
    m = RandomForestClassifier(n_estimators=100, random_state=0).fit(Xtr, ytr)
    return m, {"macro_f1": round(float(f1_score(yte, m.predict(Xte), average="macro")), 4),
               "n_train": len(Xtr), "n_test": len(Xte)}


def gate(metrics, min_f1=0.80):
    """评估门禁：macro-F1 低于阈值即不通过。"""
    return metrics["macro_f1"] >= min_f1


def save_model(model, path, metrics):
    import joblib
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    joblib.dump(model, path)
    return path


def load_model(path):
    import joblib
    if not os.path.exists(path):
        raise FileNotFoundError("模型不存在: %s" % path)
    return joblib.load(path)


def predict_one(model, feats):
    return int(model.predict([feats])[0])
