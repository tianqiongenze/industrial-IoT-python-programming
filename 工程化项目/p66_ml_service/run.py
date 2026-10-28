#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""项目唯一入口（P6 故障诊断模型与边缘部署）。

用法:
  python run.py                     # 五步流训练→门禁→落盘→教师包自检→P5联动→报告
                                    #   （fit_ms 写 runtime/train_timing.json，不入 output/）
  python run.py --serve             # 按 config 端口起 http.server 推理服务（Ctrl-C 停）
  python run.py --bench             # 强制重新实测 HTTP 推理延迟（warmup+p95，刷新缓存）
  python run.py --no-bench          # 强制读 bench.json 缓存不重测（output/ 字节不变的验收口径）
  python run.py --predict '[0.1,...]'  # 本地单条预测（30 维 JSON 数组）
  python run.py --link-p5           # 只重跑 P5 库联动回写（用已保存模型）
  python run.py --export-onnx       # A层 ONNX 导出探测/执行（离线环境如实报告不可得）
  python run.py --config X --outdir Y --quiet
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import ml_service.config as C  # noqa: E402
import ml_service.core as K  # noqa: E402
import ml_service.data as D  # noqa: E402
import ml_service.pipeline as P  # noqa: E402


def _model_path(a, cfg):
    return os.path.join(a.outdir, str(cfg.raw.get("model_name", "model_v1.joblib")))


def main(argv=None):
    ap = argparse.ArgumentParser(description="故障诊断模型与推理服务（P6）")
    ap.add_argument("--config", default=os.path.join(HERE, "config", "rules.yaml"))
    ap.add_argument("--outdir", default=os.path.join(HERE, "output"))
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--serve", action="store_true", help="启动推理服务（阻塞）")
    ap.add_argument("--bench", action=argparse.BooleanOptionalAction, default=False,
                    help="强制重新实测延迟/QPS（--no-bench 则读 bench.json 缓存，"
                         "保证 output/ 字节不变）")
    ap.add_argument("--predict", metavar="JSON", help="单条特征预测，如 '[0.0, ...30个]'")
    ap.add_argument("--link-p5", action="store_true", help="只重跑 P5 联动回写")
    ap.add_argument("--export-onnx", action="store_true", help="A层 ONNX 导出探测")
    a = ap.parse_args(argv)
    cfg = C.load_config(a.config)
    os.makedirs(a.outdir, exist_ok=True)

    if a.predict is not None:
        try:
            feats = json.loads(a.predict)
            if not isinstance(feats, list):
                raise ValueError("--predict 需 JSON 数组")
            model = K.load_model(_model_path(a, cfg))
            pred, proba = K.predict_row(model, feats, D.N_DIM)
        except (ValueError, FileNotFoundError) as exc:
            print("预测被拒绝: %s" % exc, file=sys.stderr)
            return 2
        print(json.dumps({"prediction": pred, "label": D.LABELS[pred],
                          "proba_wear": proba, "model": os.path.basename(_model_path(a, cfg))},
                         ensure_ascii=False))
        return 0

    if a.serve:
        from ml_service import service
        if not os.path.exists(_model_path(a, cfg)):
            print("模型未产出，先跑一次默认流水线", file=sys.stderr)
            P.run(cfg, a.outdir)
        service.serve_forever(cfg, _model_path(a, cfg))
        return 0

    if a.link_p5:
        import ml_service.bridge as B
        model = K.load_model(_model_path(a, cfg))
        src = P._resolve(str(cfg.raw.get("p5_db", "../p55_warehouse_orm/output/warehouse.db")))
        link = B.run_link(model, src, os.path.join(a.outdir, "warehouse_diagnosis.db"),
                          window=int(cfg.raw.get("window_size", 32)),
                          seed=int(cfg.raw.get("seed", 42)))
        print(json.dumps(link, ensure_ascii=False, indent=2))
        return 0

    if a.export_onnx:
        import ml_service.onnx_export as O
        model = K.load_model(_model_path(a, cfg))
        X, y, names, note = D.load_dataset(
            P._resolve(str(cfg.raw.get("features_path", "../../features.npy"))),
            P._resolve(str(cfg.raw.get("labels_path", "../../labels.npy"))),
            seed=int(cfg.raw.get("seed", 42)))
        status = O.export_and_compare(model, os.path.join(a.outdir, "model_v1.onnx"), X[:8])
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0

    sections = P.run(cfg, out_dir=a.outdir, bench_force=a.bench)
    if not a.quiet:
        print("\n".join(sections[-1][1]) if sections else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
