# -*- coding: utf-8 -*-
"""造数 → 训练 → 门禁 → 落盘 → 推理自检。"""
import os

from . import core, io_utils, report


def run(cfg, out_dir):
    n = int(cfg.raw.get("n_samples", 600))
    min_f1 = float(cfg.raw.get("min_f1", 0.80))
    X, y = core.make_data(n, seed=cfg.seed)
    model, metrics = core.train(X, y, float(cfg.raw.get("test_size", 0.25)), seed=cfg.seed)
    ok = core.gate(metrics, min_f1)
    if not ok:
        raise RuntimeError("评估门禁未通过：macro-F1=%.4f < %.2f，拒绝上线！"
                           % (metrics["macro_f1"], min_f1))
    os.makedirs(out_dir, exist_ok=True)
    mp = core.save_model(model, os.path.join(out_dir, "model.joblib"), metrics)
    m2 = core.load_model(mp)
    preds = [core.predict_one(m2, list(X[i])) for i in range(3)]
    result = {"metrics": metrics, "min_f1": min_f1, "model": os.path.basename(mp),
              "sample_pred": preds, "gate_passed": ok}
    io_utils.write_json(os.path.join(out_dir, "result.json"), result)
    sections = [("输入口径", ["样本 %d 条｜5 维特征｜测试占比 %.0f%%｜门禁 macro-F1≥%.2f"
                % (n, float(cfg.raw.get("test_size", 0.25)) * 100, min_f1)]),
                ("训练指标", ["macro-F1 = %.4f（训练 %d / 测试 %d）"
                          % (metrics["macro_f1"], metrics["n_train"], metrics["n_test"])]),
                ("模型产物", ["%s（joblib 落盘，可被推理服务独立加载）" % os.path.basename(mp)]),
                ("推理自检", ["前 3 条预测: %s（与真实标签 %s 对照）"
                 % (preds, [int(v) for v in y[:3]])]),
                ("结论与建议", ["门禁通过方可上线；上线后仍需监控数据漂移"])]
    report.save(sections, os.path.join(out_dir, "report.txt"))
    return sections
