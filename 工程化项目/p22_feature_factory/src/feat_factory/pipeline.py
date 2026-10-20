# -*- coding: utf-8 -*-
"""生成窗口矩阵 → 提取 17 维特征 → 固定顺序 CSV/JSON。"""
import os

from . import core, io_utils, report


def run(cfg, out_dir):
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier
    n = int(cfg.raw.get("n_windows", 40))
    image_shape = int(cfg.raw.get("image_shape", 64))
    rng = np.random.RandomState(cfg.seed)
    rows, labels = [], []
    for i in range(n):
        kind = "normal" if i % 2 == 0 else "abnormal"
        x = core.make_window(kind, size=image_shape, seed=int(rng.randint(0, 100000)))
        rows.append([round(v, 6) for v in core.feats_time(x) + core.feats_freq(x)])
        labels.append(0 if kind == "normal" else 1)
    X = np.array(rows, dtype=float)
    if np.isnan(X).any():
        raise ValueError("特征矩阵含 NaN——请检查特征函数")
    clf = RandomForestClassifier(random_state=0).fit(X, labels)
    names = core.feature_names()
    order = sorted(range(len(names)), key=lambda i: -clf.feature_importances_[i])
    os.makedirs(out_dir, exist_ok=True)
    io_utils.write_csv_rows(os.path.join(out_dir, "features.csv"),
                            [dict(zip(names, r)) for r in rows])
    result = {"n_windows": n, "n_features": len(names),
              "top": [(names[i], round(float(clf.feature_importances_[i]), 4))
                      for i in order[:int(cfg.topk)]]}
    io_utils.write_json(os.path.join(out_dir, "result.json"), result)
    sections = [("输入口径", ["窗口 %d 个｜特征 %d 维（时域13+频域4）"
                % (n, len(names))]),
                ("Top 特征", ["%d. %s = %.3f" % (k + 1, names[i], clf.feature_importances_[i])
                 for k, i in enumerate(order[:int(cfg.topk)])]),
                ("结论与建议", ["特征设计决定模型上限；把重要性最高的特征做成可解释的业务指标"])]
    report.save(sections, os.path.join(out_dir, "report.txt"))
    return sections
