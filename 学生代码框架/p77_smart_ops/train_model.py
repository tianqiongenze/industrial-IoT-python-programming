# -*- coding: utf-8 -*-
"""P7 诊断模型训练（复用P6五步流，产出入库到 data/models/）
特征口径与 tools.model_predict 对齐: [avg, max, slope, last, n/100]
运行: /opt/anaconda3/bin/python train_model.py
"""
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split

from config import CLF_FILE


def synth(n=2000, seed=7):
    rng = np.random.RandomState(seed)
    X = rng.normal(4.0, 0.5, (n, 5))
    y = rng.binomial(1, 0.4, n)
    X[y == 1, 0] += rng.uniform(1.5, 2.5, (y == 1).sum())   # 均值抬升
    X[y == 1, 1] += rng.uniform(1.0, 2.0, (y == 1).sum())   # 峰值抬升
    X[y == 1, 2] += rng.uniform(0.05, 0.15, (y == 1).sum())  # 斜率抬升
    return X, y


if __name__ == "__main__":
    X, y = synth()
    Xtr, Xte, ytr, yte = train_test_split(X, y, stratify=y, random_state=42)
    clf = RandomForestClassifier(n_estimators=200, max_depth=6, random_state=42)
    clf.fit(Xtr, ytr)
    print("F1 =", round(f1_score(yte, clf.predict(Xte)), 3))
    joblib.dump(clf, CLF_FILE, compress=3)
    print("saved:", CLF_FILE)
