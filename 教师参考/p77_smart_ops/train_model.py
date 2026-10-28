# -*- coding: utf-8 -*-
"""P7 诊断模型训练（复用P6五步流，产出入库到 data/models/）
特征口径与 tools.model_predict 对齐: [avg, max, slope, last, n/100]
运行: /opt/anaconda3/envs/pp03/bin/python train_model.py

F1 门禁：低于 MIN_F1 直接非零退出（工单P7 思政观测点"全绿才上线"——
模型不达标就不许把 joblib 覆盖进 data/models/，防止带病模型被平台加载）。
"""
import os
import sys

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split

from config import CLF_FILE

MIN_F1 = float(os.environ.get("MIN_F1", "0.80"))
FEATURE_ORDER = ["avg_vib", "max_vib", "slope", "last_vib", "samples/100"]


def synth(n=2000, seed=7):
    rng = np.random.RandomState(seed)
    X = rng.normal(4.0, 0.5, (n, 5))
    y = rng.binomial(1, 0.4, n)
    X[y == 1, 0] += rng.uniform(1.5, 2.5, (y == 1).sum())   # 均值抬升
    X[y == 1, 1] += rng.uniform(1.0, 2.0, (y == 1).sum())   # 峰值抬升
    X[y == 1, 2] += rng.uniform(0.05, 0.15, (y == 1).sum())  # 斜率抬升
    return X, y


def train(X, y):
    Xtr, Xte, ytr, yte = train_test_split(X, y, stratify=y, random_state=42)
    clf = RandomForestClassifier(n_estimators=200, max_depth=6, random_state=42)
    clf.fit(Xtr, ytr)
    return clf, float(f1_score(yte, clf.predict(Xte)))


if __name__ == "__main__":
    X, y = synth()
    clf, f1 = train(X, y)
    print("F1 =", round(f1, 3), "| 门禁线 =", MIN_F1, "| 特征口径 =", FEATURE_ORDER)
    if f1 < MIN_F1:
        print(f"[gate] 拒绝上线：F1={f1:.3f} < {MIN_F1}（不覆盖已有模型文件）")
        sys.exit(1)
    joblib.dump(clf, CLF_FILE, compress=3)
    print("saved:", CLF_FILE)
