# -*- coding: utf-8 -*-
"""分层工单闸门（D/C/B/A）与墙钟隔离测试（对齐 p41_collector_hub 同类测试风格）。

在真实流水线上逐条拿出达标证据：tiers 布尔、报告「分层达标」行数字、
可解释性表镜像进 result.json；并证明 fit_ms（墙钟）只落 runtime/，
--no-bench 保持 output/ 字节不变。
"""
import importlib.util
import json
import os
import re

import pytest

from ml_service import config as C
import ml_service.pipeline as P

HERE = os.path.dirname(os.path.abspath(__file__))
RUN_PY = os.path.join(HERE, "..", "run.py")

_CFG_KEYS = """
features_path: {tmp}/none.npy
labels_path: {tmp}/none.npy
teacher_model: {tmp}/none.joblib
p5_db: {tmp}/none.db
model_name: model_v1.joblib
n_features: 30
n_fallback: 120
seed: 42
test_size: 0.25
cv_folds: 3
min_f1: 0.80
grid_n_estimators: [50]
grid_max_depth: [4]
port: 0
host: "127.0.0.1"
bench_requests: 12
warmup: 2
window_size: 24
teacher_samples: 10
explain_topk: {topk}
"""


def _write_cfg(tmp_path, topk=3):
    p = os.path.join(str(tmp_path), "rules_%d.yaml" % topk)
    with open(p, "w", encoding="utf-8") as f:
        f.write(_CFG_KEYS.format(tmp=str(tmp_path), topk=topk))
    return p


def _run(tmp_path, out_name="out", topk=3):
    out = os.path.join(str(tmp_path), out_name)
    cfg = C.load_config(_write_cfg(tmp_path, topk))
    sections = P.run(cfg, out)
    data = json.loads(open(os.path.join(out, "result.json"),
                           encoding="utf-8").read())
    text = open(os.path.join(out, "report.txt"), encoding="utf-8").read()
    return out, data, text, sections


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return _run(tmp_path_factory.mktemp("tier"), "out")


def test_tiers_all_four_pass_with_real_numbers(built):
    _out, data, text, sections = built
    assert set(data["tiers"]) == {"D", "C", "B", "A"}
    assert all(data["tiers"][k] is True for k in "DCBA")
    assert dict(sections)["分层达标"] == [
        line for line in text.splitlines() if re.match(r"^[DCBA]层 ", line)]
    for prefix in ("D层 学徒", "C层 操作员", "B层 组长", "A层 师傅"):
        line = next(l for l in text.splitlines() if l.startswith(prefix))
        assert "→ 达标" in line and re.search(r"\d", line)


def test_c_layer_f1_and_b_layer_link_numbers(built):
    _out, data, text, _ = built
    ev, link = data["evaluate"], data["p5_link"]
    assert ("C层 操作员·F1≥0.80 并保存: 定选 %s 测试集 macro-F1=%.4f"
            % (ev["best_model"], ev["test_macro_f1"])) in text
    assert "P5 联动回写 %d 条" % link["diagnosed_records"] in text
    assert data["gate"]["macro_f1"] >= 0.80 and link["diagnosed_records"] > 0


def test_a_layer_explain_table_mirrored_in_result_json(built):
    _out, data, text, _ = built
    for name in ("LR", "RF", "GBM", "RF-tuned"):
        top = data["evaluate"]["comparison"][name]["explain"]["top"]
        assert len(top) == 3
        assert top[0]["feature"] in text
        assert "%.6f" % top[0]["abs_value"] in text
    assert "训练耗时(fit_ms)已写入 runtime/train_timing.json（墙钟实测，不入 output/）" in text


def test_result_json_has_no_wallclock_keys(built):
    """墙钟红线：result.json 全文无 fit_ms；evaluate/gate/tiers 子树无 *_ms 键。"""
    out, data, _text, _ = built
    raw = open(os.path.join(out, "result.json"), encoding="utf-8").read()
    assert "fit_ms" not in raw

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)

    keys = (set(walk(data["evaluate"])) | set(walk(data["gate"]))
            | set(walk(data["tiers"])))
    assert not [k for k in keys if k.endswith("_ms")
                or "fit" in k or "elapsed" in k or "duration" in k]


def test_fit_ms_written_to_runtime_not_output(built):
    out, _data, _text, _ = built
    runtime = os.path.join(os.path.dirname(out), "runtime", "train_timing.json")
    assert os.path.exists(runtime)
    assert not os.path.exists(os.path.join(out, "runtime"))
    assert not [f for f in os.listdir(out) if "timing" in f]
    t = json.loads(open(runtime, encoding="utf-8").read())
    assert set(t["models"]) == {"LR", "RF", "GBM", "RF-tuned(grid)"}
    assert all(v > 0 for v in t["models"].values())
    assert "墙钟" in t["note"]


def test_explain_topk_is_config_only_knob(tmp_path):
    """改配置不改代码：explain_topk 3→5，Top-5 清单即随之变化。"""
    _out, data, _text, _ = _run(tmp_path, "out5", topk=5)
    for name in ("LR", "RF", "GBM", "RF-tuned"):
        ex = data["evaluate"]["comparison"][name]["explain"]
        assert ex["k"] == 5 and len(ex["top"]) == 5


def _entry():
    spec = importlib.util.spec_from_file_location("p66_run", RUN_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _norm(out):
    rep = open(os.path.join(out, "report.txt"), encoding="utf-8").read()
    rep = "\n".join(l for l in rep.splitlines() if not l.startswith("生成时间"))
    rep = re.sub(r"trained_at\(UTC\)=[\d:T-]+", "X", rep)
    res = json.loads(open(os.path.join(out, "result.json"), encoding="utf-8").read())
    res["manifest"]["trained_at_utc"] = "X"
    return rep, json.dumps(res, ensure_ascii=False, sort_keys=True)


def test_no_bench_keeps_output_bytes_identical(tmp_path):
    """--no-bench：读 bench.json 缓存不重测 ⇒ output/ 除显式时间戳外字节不变；
    fit_ms 每次刷新只写 runtime/，绝不污染 output/。"""
    mod = _entry()
    cfg = _write_cfg(tmp_path)
    out = os.path.join(str(tmp_path), "out_cli")
    assert mod.main(["--config", cfg, "--outdir", out, "--quiet"]) == 0
    snap = (open(os.path.join(out, "bench.json"), encoding="utf-8").read(),)
    norm1 = _norm(out)
    rt1 = json.loads(open(os.path.join(os.path.dirname(out), "runtime",
                                       "train_timing.json"), encoding="utf-8").read())
    assert mod.main(["--config", cfg, "--no-bench", "--outdir", out,
                     "--quiet"]) == 0
    bench2 = open(os.path.join(out, "bench.json"), encoding="utf-8").read()
    assert bench2 == snap[0]                      # 缓存未被重测刷新
    assert _norm(out) == norm1                    # 除时间戳外 output/ 一致
    rt2 = json.loads(open(os.path.join(os.path.dirname(out), "runtime",
                                       "train_timing.json"), encoding="utf-8").read())
    assert rt2["models"].keys() == rt1["models"].keys()
