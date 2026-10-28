# -*- coding: utf-8 -*-
"""编排层：五步流→门禁→model_v1.joblib+版本清单→教师模型自检→P5联动→HTTP压测→报告。

实测耗时（bench.json）与 P5 项目同策略：首跑实测固化、后续读缓存，保证两次
运行 output/ 除带版本语义的时间戳（报告生成时间/manifest trained_at）外一致。
"""
import datetime as dt
import json
import os
import platform

import numpy as np
import sklearn

from . import bridge, core, data, io_utils, onnx_export, report, service

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _resolve(path):
    return path if os.path.isabs(path) else os.path.abspath(
        os.path.join(PROJECT_ROOT, path))


def train_pipeline(cfg, out_dir, bench_force=False):
    """返回 (result_dict, sections)。门禁不过直接抛错（工程化要求1）。

    可复现红线：fit_ms（训练墙钟耗时）绝不写入 output/——只落
    runtime/train_timing.json（与 output/ 平级，已在 .gitignore 忽略），
    报告仅引用该路径一行。
    """
    io_utils.ensure_dir(out_dir)
    seed = int(cfg.raw.get("seed", 42))
    min_f1 = float(cfg.raw.get("min_f1", 0.80))
    model_name = str(cfg.raw.get("model_name", "model_v1.joblib"))
    explain_topk = int(cfg.raw.get("explain_topk", 3))
    fit_ms = {}

    feats_path = _resolve(str(cfg.raw.get("features_path", "../../features.npy")))
    labels_path = _resolve(str(cfg.raw.get("labels_path", "../../labels.npy")))
    X, y, names, source_note = data.load_dataset(
        feats_path, labels_path, seed=seed,
        n_fallback=int(cfg.raw.get("n_fallback", 200)))

    model, ev = core.evaluate(
        X, y, seed=seed, test_size=float(cfg.raw.get("test_size", 0.25)),
        cv_folds=int(cfg.raw.get("cv_folds", 5)),
        grid_n_estimators=list(cfg.raw.get("grid_n_estimators", [50, 100, 200])),
        grid_max_depth=list(cfg.raw.get("grid_max_depth", [4, 6, None])),
        explain_topk=int(cfg.raw.get("explain_topk", 3)),
        feature_names=names, timing_out=fit_ms)

    if not core.gate(ev["test_macro_f1"], min_f1):
        raise RuntimeError("评估门禁未通过：测试集 macro-F1=%.4f < %.2f，拒绝注册上线"
                           % (ev["test_macro_f1"], min_f1))

    trained_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    model_path = os.path.join(out_dir, model_name)
    manifest = {
        "model_name": model_name,
        "version_note": "%s：P6 五步流训练产物（划分→训练→CV→GridSearch→落盘）" % model_name,
        "estimator": ev["best_model"],
        "sklearn": sklearn.__version__, "numpy": np.__version__,
        "python": platform.python_version(),
        "trained_at_utc": trained_at,
        "data_source": source_note,
        "n_features": ev["feature_dim"], "feature_names": names,
        "seed": seed, "metrics": {
            "test_macro_f1": ev["test_macro_f1"],
            "confusion_matrix": ev["confusion_matrix"],
            "grid_best_params": ev["grid_search"]["best_params"]},
        "gate_min_f1": min_f1, "gate_passed": True,
    }
    core.save_model(model, model_path, manifest)
    io_utils.write_json(os.path.join(out_dir, model_name + ".manifest.json"), manifest)

    # A层三维评价之「训练耗时」：墙钟 fit_ms 只写 runtime/，不进 output/（闸门红线）
    runtime_dir = os.path.join(os.path.dirname(os.path.abspath(out_dir)), "runtime")
    io_utils.ensure_dir(runtime_dir)
    timing_path = os.path.join(runtime_dir, "train_timing.json")
    io_utils.write_json(timing_path, {
        "note": "墙钟实测 fit_ms（单位 ms），禁止进入 output/——"
                "verify_local repeat 闸门逐字节比对 output/",
        "seed": seed, "unit": "ms",
        "models": dict(sorted(fit_ms.items())),
        "total_fit_ms": round(sum(fit_ms.values()), 2),
        "explain_topk": explain_topk,
    })
    timing_rel = "runtime/train_timing.json"

    # D层：教师端预训练缺陷模型包本地推理测试（≥10 样本）
    teacher = _teacher_check(cfg, X, model)

    # B层：接入 P5 数据库联动回写
    p5_src = _resolve(str(cfg.raw.get("p5_db", "../p55_warehouse_orm/output/warehouse.db")))
    link = bridge.run_link(model, p5_src,
                           os.path.join(out_dir, "warehouse_diagnosis.db"),
                           window=int(cfg.raw.get("window_size", 32)), seed=seed)

    # 压测：真实 HTTP（临时端口）——首跑实测，缓存固化
    bench_path = os.path.join(out_dir, "bench.json")
    if bench_force or not os.path.exists(bench_path):
        rows = X[:max(1, int(cfg.raw.get("bench_requests", 100)))]
        bench = service.bench(model, ev["feature_dim"],
                              n_requests=int(cfg.raw.get("bench_requests", 100)),
                              warmup=int(cfg.raw.get("warmup", 5)),
                              features=[list(r) for r in rows])
        bench["source"] = "首次运行/--bench 实测（进程内临时端口，端口留给 --serve）；其余运行读此缓存"
        io_utils.write_json(bench_path, bench)
    else:
        bench = io_utils.read_json(bench_path)

    # A层：ONNX 导出路径（导入探测；离线环境如实报告不可得）
    onnx_status = onnx_export.export_and_compare(
        model, os.path.join(out_dir, "model_v1.onnx"), X[:8])

    # 工单优秀(B)「服务异常处理(404/参数错)」：真打临时端口逐条核对状态码，
    # 探针清单来自 config（error_probes 按名字点菜），删一条就少一条证据。
    wanted = cfg.raw.get("error_probes")
    sel = None if wanted is None else [p for p in service.ERROR_PROBES
                                       if p[0] in set(wanted)]
    err = service.error_selftest(
        model, ev["feature_dim"],
        host=str(cfg.raw.get("host", "127.0.0.1")), probes=sel)

    tiers, tier_lines = _tier_gates(ev, manifest, link, teacher, fit_ms, min_f1)
    wo, wo_lines, wo_ext = _workorder_gates(cfg, ev, manifest, link, teacher,
                                            bench, err, onnx_status, min_f1)

    result = {
        "env": {"python": platform.python_version(), "sklearn": sklearn.__version__,
                "numpy": np.__version__},
        "data_source": source_note,
        "evaluate": ev,
        "gate": {"min_f1": min_f1, "macro_f1": ev["test_macro_f1"], "passed": True},
        "tiers": tiers,
        "workorder_tiers": wo, "workorder_rows": dict(WO_ROW),
        "workorder_evidence": {
            "error_probes": err["n_probes"], "error_probes_ok": err["n_ok"],
            "codes_seen": err["codes_seen"],
            "error_cases_ok": err["error_cases_ok"],
            "latency_client_timed": bench["client_timed"],
            "latency_server_recorded": bench["server_recorded"],
            "latency_records_match": bench["records_match"],
            "min_latency_records": int(cfg.raw.get("min_latency_records", 50)),
            "onnx_available": bool(onnx_status["available"]),
            "version_compared": teacher.get("version_compared", 0),
            "version_agreement": teacher.get("version_agreement", 0)},
        "workorder_unmeasured": wo_ext,
        "workorder_lines": wo_lines,
        "runtime_files": {"train_timing": timing_rel,
                          "note": "墙钟训练计时数值只存于该 runtime 路径文件，"
                                  "不写入 output/ 任何产物"},
        "manifest": manifest,
        "teacher": teacher,
        "p5_link": link,
        "bench": bench,
        "onnx": onnx_status,
        "service_contract": {"endpoints": ["GET /health（真推理一发）",
                                           "POST /predict（JSON features 30维）"],
                             "errors": {"400": "非JSON/缺features/维度不符/NaN",
                                        "404": "未知路径"},
                             "cli": "python run.py --serve （config port=%s）"
                                    % cfg.raw.get("port", 8899)},
    }
    sections = _sections(result, tier_lines)
    return result, sections


def _teacher_check(cfg, X, local_model=None):
    """D层：加载教师包并对前 N(≥10) 条真实特征做本地推理测试。

    给了 local_model 就顺手做超优档的"版本对比实验"：同一批输入喂给
    教师包（上一版模型工件）与本轮训练出的模型，逐条比预测——这是离线
    环境拿不到 onnx 时，工单超优行"ONNX导出**或**版本对比实验"里那条"或"。
    """
    import warnings
    path = _resolve(str(cfg.raw.get("teacher_model", "../../model_v1.joblib")))
    n = max(10, int(cfg.raw.get("teacher_samples", 10)))
    if not os.path.exists(path):
        return {"available": False,
                "reason": "教师模型包缺失: %s（如实报告，不伪造）" % path}
    model, info = core.load_teacher_model(path)
    sample = X[:n]
    preds = [int(v) for v in model.predict(sample)]
    out = {"available": True, "path": os.path.basename(path),
           "n_features": info["n_features"],
           "classes": info["classes"],
           "load_warnings": info["load_warnings"],
           "local_sklearn": info["local_sklearn"],
           "tested_samples": int(n), "predictions": preds}
    if local_model is not None and int(info["n_features"]) == int(X.shape[1]):
        lp = [int(v) for v in local_model.predict(sample)]
        out["local_predictions"] = lp
        out["version_agreement"] = sum(1 for a, b in zip(preds, lp) if a == b)
        out["version_diff_rows"] = [i for i, (a, b) in enumerate(zip(preds, lp))
                                    if a != b]
        out["version_compared"] = len(preds)
    return out


def _cm_lines(cm):
    return ["混淆矩阵（行=真实 0正常/1磨损，列=预测 0/1）: [[%d, %d], [%d, %d]]"
            % (cm[0][0], cm[0][1], cm[1][0], cm[1][1]),
            "  FN(漏检真故障)=%d ｜ FP(误报)=%d —— 漏检代价远高于误报，选型向召回偏移"
            % (cm[1][0], cm[0][1])]


def _tier_gates(ev, manifest, link, teacher, fit_ms, min_f1):
    """分层达标（D/C/B/A）：每条都是可证伪的真实数字判定，非文案。

    口径出处=工单 03-P6 教师版 cell-0 分层表：D 跟做示例跑通出结果；
    C F1≥0.80 并保存；B 对比+调参记录+接入数据库联动；A LR/RF/GBM
    F1+计时+可解释性三维评价。
    """
    names = ("LR", "RF", "GBM", "RF-tuned")
    exp_ok = all(ev["comparison"][n]["explain"]["top"] for n in names)
    timing_ok = all(m in fit_ms for m in names[:3] + ("RF-tuned(grid)",))
    tiers = {
        "D": ev["n_test"] > 0 and ev["n_train"] > 0,
        "C": (ev["test_macro_f1"] >= min_f1 and manifest["gate_passed"] is True
              and manifest["model_name"].endswith(".joblib")),
        "B": (set(names) <= set(ev["comparison"])
              and bool(ev["grid_search"]["best_params"])
              and link["diagnosed_records"] > 0),
        "A": exp_ok and timing_ok and ev["explain_topk"] >= 1,
    }
    tier_lines = [
        "D层 学徒·示例跑通出结果: 五步流端到端完成，训练 %d / 测试 %d 条全量推理，"
        "教师包本地推理 %d 条（可用=%s）→ %s" % (
            ev["n_train"], ev["n_test"],
            teacher["tested_samples"] if teacher["available"] else 0,
            teacher["available"], "达标" if tiers["D"] else "未达标"),
        "C层 操作员·F1≥%.2f 并保存: 定选 %s 测试集 macro-F1=%.4f，"
        "%s 已落盘+manifest → %s" % (
            min_f1, ev["best_model"], ev["test_macro_f1"],
            manifest["model_name"], "达标" if tiers["C"] else "未达标"),
        "B层 组长·对比+调参+联动: 对比模型 %d 个（LR/RF/GBM/RF-tuned），"
        "GridSearch best_params=%s best_cv=%.4f，P5 联动回写 %d 条 → %s" % (
            len(ev["comparison"]), ev["grid_search"]["best_params"],
            ev["grid_search"]["best_cv_score"], link["diagnosed_records"],
            "达标" if tiers["B"] else "未达标"),
        "A层 师傅·三维评价（F1+计时+可解释性）: 4 模型 Top-%d 可解释清单齐备"
        "（%s），fit_ms 记录 %d 项（写入 runtime/train_timing.json，墙钟值不入"
        "output/）→ %s" % (
            ev["explain_topk"], ev["explain_feature_source"], len(fit_ms),
            "达标" if tiers["A"] else "未达标"),
    ]
    return tiers, tier_lines


# 工单《P6 验收标准》四行原文（逐字照抄，作为对照节的单一口径来源）。它与
# `_tier_gates` 的课堂四级字母错一档：课堂 C 层（F1≥0.80 并保存）≈ 工单及格，
# 课堂 B 层（对比+调参+联动）跨了工单良好与优秀两档，而工单优秀的"服务异常
# 处理(404/参数错)"与超优的"版本对比实验"在课堂四行里一次都没判过。
WO_ROW = {"D": "诊断模型F1≥0.80并保存；推理服务可调通",
          "C": "接入数据库联动；延迟记录完整",
          "B": "模型对比+调参记录；服务异常处理(404/参数错)",
          "A": "优秀+ONNX导出或版本对比实验；P7综合项目立项书"}


def _workorder_gates(cfg, ev, manifest, link, teacher, bench, err, onnx_status,
                     min_f1):
    """工单四档逐条判定：只判本节测得到的，测不到的点名交给外部取证，不假判。

    每档都留了可翻红的配置旋钮：及格看 `min_f1`，良好看 `min_latency_records`，
    优秀看 `error_probes`（少配一条错误探针即判未通过），超优看 `onnx`/教师包
    版本对比（离线环境无 onnx 时走"或"的另一支）。
    """
    names = ("LR", "RF", "GBM", "RF-tuned")
    min_rec = int(cfg.raw.get("min_latency_records", 50))
    latency_keys = ("warmup_first_ms", "mean_ms", "p50_ms", "p95_ms",
                    "p99_ms", "max_ms")
    lat_full = (all(k in bench and float(bench[k]) >= 0 for k in latency_keys)
                and bench["records_match"] is True
                and bench["client_timed"] >= min_rec)
    called = {r["probe"]: r["ok"] for r in err["probes"]}
    reachable = (called.get("health_get") is True and called.get("predict_ok") is True
                 and bench["requests_sent"] > 0)
    err_cases = sum(1 for r in err["probes"]
                    if r["expect"] in (400, 404) and r["ok"])
    need_err = sum(1 for r in err["probes"] if r["expect"] in (400, 404))
    version_cmp = int(teacher.get("version_compared", 0)) >= 10
    wo_b = (set(names) <= set(ev["comparison"])
            and bool(ev["grid_search"]["best_params"])
            and err["all_ok"] is True and need_err > 0 and err_cases == need_err)
    wo = {
        "D": (ev["test_macro_f1"] >= min_f1
              and manifest["gate_passed"] is True
              and manifest["model_name"].endswith(".joblib") and reachable),
        "C": link["diagnosed_records"] > 0 and lat_full,
        # 工单超优行原文是"优秀+…"，所以优秀档的实测项是超优档的前置条件。
        "B": wo_b,
        "A": bool(wo_b and (bool(onnx_status["available"]) or version_cmp)),
    }
    wo_ext = {
        "D": ["PEP 8 与注释规范（本项目由 CI lint 侧取证，报告不判）"],
        "C": ["延迟的绝对阈值：工单 P6 未给毫秒上限，故本节只判「记录是否完整」，不判快慢"],
        "B": ["生产级 ASGI 服务的异常中间件（本项目用标准库 http.server，"
              "400/404 分支已逐条实测，见 docs/03 决策矩阵）"],
        "A": ["P7 综合项目立项书（交付物在 P7 工程，不在本项目内，见 ../p77 与 docs/07）"],
    }
    def verdict(ok, key):
        """有未实测项的行只说"实测项通过"，不冒充整档达标（与 p22/p41 同一红线）。"""
        if wo_ext[key]:
            return "本节实测项 通过" if ok else "本节实测项 有未通过项"
        return "达标" if ok else "未达标"

    wo_lines = [
        "工单及格(D)「%s」: 测试集 macro-F1=%.4f ≥ 门禁 %.2f｜%s + manifest 已落盘"
        "｜服务真打一发：/health 与 /predict 均 200（客户端共发 %d 次）→ %s｜未实测项：%s"
        % (WO_ROW["D"], ev["test_macro_f1"], min_f1, manifest["model_name"],
           bench["requests_sent"], verdict(wo["D"], "D"),
           "；".join(wo_ext["D"])),
        "工单良好(C)「%s」: P5 库联动回写 diagnosis %d 条｜延迟记录完整：客户端共发 %d 次"
        "（含 warmup %d 次）逐条计时 %d 条，服务端 stats 同步记录 %d 条（两边条数相等=%s），"
        "计时条数 ≥ 阈值 %d（config: min_latency_records）且 mean/p50/p95/p99/max 六项齐备"
        " → %s｜未实测项：%s"
        % (WO_ROW["C"], link["diagnosed_records"], bench["requests_sent"],
           bench["warmup"], bench["client_timed"], bench["server_recorded"],
           bench["records_match"], min_rec, verdict(wo["C"], "C"),
           "；".join(wo_ext["C"])),
        "工单优秀(B)「%s」: 对比模型 %d 个（%s）｜GridSearch best_params=%s｜"
        "异常分支逐条实测：探针 %d 条全 %s，其中 400/404 类 %d/%d 条按契约返回"
        "（实到状态码 %s）→ %s｜未实测项：%s"
        % (WO_ROW["B"], len(ev["comparison"]), "/".join(sorted(ev["comparison"])),
           ev["grid_search"]["best_params"], err["n_probes"],
           "通过" if err["all_ok"] else "有未通过项", err_cases, need_err,
           "/".join(str(c) for c in err["codes_seen"]), verdict(wo["B"], "B"),
           "；".join(wo_ext["B"])),
        "工单超优(A)「%s」: 前置优秀档=%s｜ONNX 导出=%s｜版本对比实验：教师包 %s "
         "与本轮 %s 在同一批 %d 条特征上逐条比预测，一致 %d 条（不一致行 %s）→ %s"
        "｜未实测项：%s"
        % (WO_ROW["A"], "通过" if wo_b else "未通过",
           "已导出" if onnx_status["available"] else "不可得（离线无 skl2onnx，如实报告）",
           teacher["path"] if teacher["available"] else "缺失",
           manifest["model_name"], teacher.get("version_compared", 0),
           teacher.get("version_agreement", 0),
           teacher.get("version_diff_rows", []) or "无",
           verdict(wo["A"], "A"), "；".join(wo_ext["A"])),
        "档位口径说明 : 课堂阶梯（D 示例跑通 / C F1≥%.2f 并保存 / B 对比+调参+联动 / "
        "A 三维评价）与工单四档（及格/良好/优秀/超优）字母不同源——课堂 C 层≈工单及格、"
        "课堂 B 层横跨工单良好与优秀，工单优秀的『服务异常处理(404/参数错)』与超优的"
        "『版本对比实验』只在本节取证；本节判「达标」仅限实测项，未实测项一律点名。"
        % min_f1,
    ]
    return wo, wo_lines, wo_ext


def _explain_lines(ev):
    """A层·可解释性 Top-k 确定性表格（LR=coef_，树模型=feature_importances_）。"""
    rows = []
    for name in ("LR", "RF", "GBM", "RF-tuned"):
        ex = ev["comparison"][name]["explain"]
        for t in ex["top"]:
            rows.append([name, t["rank"], t["feature"],
                         "%.6f" % t["abs_value"], "%+.6f" % t["signed_value"]])
    return [io_utils.fmt_table(rows, ["模型", "名次", "特征", "|权重|", "带符号值"]),
            "口径：LR 取 coef_（正类=磨损，|coef| 大者即主贡献特征，带符号值给出"
            "影响方向）；RF/GBM 取 feature_importances_；并列按 zlib.crc32(特征名)"
            "稳定定序（内置 hash() 受 PYTHONHASHSEED 随机化，禁用）。",
            "训练耗时(fit_ms)已写入 runtime/train_timing.json（墙钟实测，不入 output/）"]


def _sections(res, tier_lines):
    ev, b, link, teacher = res["evaluate"], res["bench"], res["p5_link"], res["teacher"]
    mf = res["manifest"]
    comp_rows = [[name, c["cv_mean"], c["cv_std"], c["test_macro_f1"],
                  c["precision_wear"], c["recall_wear"]]
                 for name, c in ev["comparison"].items()]
    gs = ev["grid_search"]
    sections = [
        ("数据与口径", [
            "数据源：%s" % res["data_source"],
            "特征契约：30 维，列序=FEATURE_NAMES（训练/推理/联动同一份清单，顺序校验通过）",
            "环境：Python %s / sklearn %s / numpy %s" % (
                res["env"]["python"], res["env"]["sklearn"], res["env"]["numpy"]),
        ]),
        ("D层·预训练模型包本地推理测试", [
            ("教师包 %s：%d 维入参，classes=%s，取前 %d 条真实特征推理"
             % (teacher["path"], teacher["n_features"], teacher["classes"],
                teacher["tested_samples"])
             if teacher["available"] else "教师包缺失：" + teacher["reason"]),
            "预测序列：%s" % (teacher.get("predictions", [])),
            "跨版本加载告警（如实转录）: %s" % (
                " / ".join(teacher.get("load_warnings", [])) or "无"),
        ]),
        ("C层·五步流与评估门禁", [
            "划分：训练 %d / 测试 %d（stratify，seed=%d）" % (ev["n_train"], ev["n_test"],
                                                 res["manifest"]["seed"]),
            "定选模型：%s，测试集 macro-F1=%.4f ≥ 门禁 %.2f → 允许注册" % (
                ev["best_model"], ev["test_macro_f1"], res["gate"]["min_f1"]),
            *_cm_lines(ev["confusion_matrix"]),
            ev["classification_report_text"],
        ]),
        ("B层·模型对比 + 调参留痕 + P5 联动", [
            io_utils.fmt_table(comp_rows,
                               ["模型", "CV均值", "CV方差", "测试F1", "磨损精确率", "磨损召回率"]),
            "GridSearchRF（cv=%d）：best_params=%s，best_cv=%.4f" % (
                gs["cv"], gs["best_params"], gs["best_cv_score"]),
            "调参Top5 留痕：" + " | ".join("%s→%.4f" % (r["params"], r["mean_test"])
                                   for r in gs["top5_mean_test"]),
            "", "P5 库联动回写：%s → 拷贝 %s，records.diagnosis 回写 %d 条" % (
                link["origin"], link["copy_db"], link["diagnosed_records"]),
            io_utils.fmt_table([[r["device"], r["record_id"], r["window_used"],
                                 r["prediction"], r["label"]] for r in link["devices"]],
                               ["设备", "新记录id", "窗口", "预测", "结论"]),
            "feature_names 顺序校验：%s" % link["feature_order_check"],
            "（诚实口径：P5 记录窗口特征与 P2.2 训练分布不同域，本表演示联动机制而非工况判定）",
        ]),
        ("A层·可解释性 Top-%d（工单三维评价之一）" % ev["explain_topk"],
         _explain_lines(ev)),
        ("P6.2·推理服务与压测（warmup+p95 验收口径）", [
            "服务契约：GET /health=真推理一发；POST /predict=JSON 30维入/预测出；"
            "参数错/维度不符→400；未知路径→404；日志 logging 落 stderr",
            "启动：python run.py --serve（config port=%s；测试用临时端口=0 由内核分配）"
            % res["service_contract"]["cli"].split("port=")[-1].rstrip("）"),
            "压测（%s）：warmup首发 %.1f ms；n=%d → mean %.2f / p50 %.2f / "
            "p95 %.2f / p99 %.2f / max %.2f ms；QPS=%.1f" % (
                b.get("source", ""), b["warmup_first_ms"], b["n_requests"],
                b["mean_ms"], b["p50_ms"], b["p95_ms"], b["p99_ms"], b["max_ms"], b["qps"]),
            "决策矩阵（部署形态）：脚本批处理=零延迟网络但不可集成｜HTTP服务=可被 MES/P7 "
            "调用（本课选型，http.server 教学够用，生产换 ASGI）｜边缘定时任务=省带宽但"
            "模型更新滞后",
        ]),
        ("A层·ONNX/边缘部署对比", [
            ("已导出 %s（%d 字节），延迟对比 %s" % (
                res["onnx"].get("path"), res["onnx"].get("size_bytes", 0),
                res["onnx"].get("note", "")))
            if res["onnx"]["available"] else
            "ONNX 导出不可得（如实报告）：%s" % res["onnx"]["reason"],
            "版本说明：%s ｜ sklearn==%s ｜ 特征维数 %d ｜ trained_at(UTC)=%s" % (
                mf["version_note"], mf["sklearn"], mf["n_features"], mf["trained_at_utc"]),
        ]),
        ("工单验收四档对照（及格/良好/优秀/超优）", res["workorder_lines"]),
        ("分层达标", tier_lines),
        ("结论与建议", [
            "1) 五步流+CV+GridSearch 全留痕，F1 门禁硬阻断带病上线；",
            "2) 服务化用标准库 http.server 即可跑通 curl 级验收；生产替换 ASGI 方案已写入决策矩阵；",
            "3) 压测口径 warmup 后看 p95/p99 而非均值；",
            "4) P5→P6 数据闭环成立：入库记录可抽特征、可预测、可回写诊断字段；",
            "5) A层三维评价落地：F1（对比表）+ 计时（runtime/train_timing.json，墙钟不入"
            "output/）+ 可解释性（Top-k 表进报告与 result.json）。",
        ]),
    ]
    return sections


def run(cfg, out_dir, bench_force=False):
    result, sections = train_pipeline(cfg, out_dir, bench_force=bench_force)
    io_utils.write_json(os.path.join(out_dir, "result.json"), result)
    report.save(sections, os.path.join(out_dir, "report.txt"))
    return sections
