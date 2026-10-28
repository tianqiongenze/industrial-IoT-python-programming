# -*- coding: utf-8 -*-
"""教师版 P7 端到端测试：按 ABCD 分层断言 + 五处工单点位（P7-1…P7-5）的参考答案。

运行: /opt/anaconda3/envs/pp03/bin/python -m pytest -q -p no:cacheprovider
分层口径（对齐 W09_P7 智能运维平台综合项目分层工单）：
  C 层 = 台账/时序/向量三处点位的参考答案可用（test_todo_c_*）
  B 层 = 图影响路径 + ReAct 循环 + 结案结构化（test_todo_b_*）
  D 层 = 四个 API 的契约（含错误路径不 500），用 litestar 测试客户端，免起端口
  A 层 = 嵌入后端可切换 + 召回对比脚本可跑（test_tier_a_*）
可选依赖缺失时按层 skip，不谎报通过。conftest.py 已把五库路径指向一次性临时目录。
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = str(Path(__file__).resolve().parents[1])


# ---------------------------------------------------------------- 五库播种（会话级）
@pytest.fixture(scope="session")
def seeded():
    pytest.importorskip("duckdb")
    pytest.importorskip("kuzu")
    pytest.importorskip("chromadb")
    import joblib
    from stores import graph, relational, timeseries, vector_store
    from train_model import CLF_FILE, synth, train
    relational.build_seed()
    timeseries.seed()
    graph.seed()
    vector_store.seed()
    clf, f1 = train(*synth())
    assert f1 >= 0.80, "模型门禁未过就不该入库"
    joblib.dump(clf, CLF_FILE, compress=3)
    return True


# ------------------------------------------------------------------ 工单点位 P7-1/2/4（C 层）
def test_todo_c1_relational_profile(seeded):
    from stores.relational import device_profile, journal_mode
    d = device_profile("PUMP-03")
    assert d["code"] == "PUMP-03" and d["line"] == "LINE-A2"
    assert {p["tag"] for p in d["points"]} == {"vib_rms", "pressure", "temp"}
    assert d["alerts"][0]["level"] == "warn"
    assert journal_mode() == "wal", "README/决策矩阵宣称 WAL，必须实测为 wal"


def test_todo_c1_unknown_device_no_crash(seeded):
    from stores.relational import device_profile
    d = device_profile("NOPE-99")
    assert "error" in d and d["code"] == "NOPE-99"          # 边界：查无设备返回结构化错误


def test_todo_c2_window_feats(seeded):
    from stores.timeseries import window_feats
    f = window_feats("PUMP-03", 10)
    assert f["samples"] > 0 and f["avg_vib"] > 0 and f["max_vib"] >= f["avg_vib"]
    assert set(f) >= {"samples", "avg_vib", "max_vib", "slope", "last_vib"}


def test_todo_c2_empty_window_boundary(seeded):
    from stores.timeseries import window_feats
    f = window_feats("NOPE-99")                             # 空输入边界
    assert f["samples"] == 0 and f["avg_vib"] == 0.0 and "note" in f
    window_feats("PUMP-03", 0)                              # 极值：minutes=0 不得抛异常


def test_todo_c2_asof_grid(seeded):
    from stores.timeseries import asof_grid
    g = asof_grid("PUMP-03")
    assert 0 < len(g) <= 5 and {"grid", "ts", "vib"} <= set(g[0])


def test_todo_c4_vector_recall(seeded):
    from stores.vector_store import search
    r = search("泵振动持续变大怎么办", 2)
    assert len(r) == 2 and {"case", "meta", "dist"} <= set(r[0])
    assert all(x["dist"] >= 0 for x in r)
    assert search("激光对中", 1)[0]["meta"]["action"] == "激光对中"


def test_todo_c4_embedding_cross_process_deterministic(seeded):
    """回归：曾用内置 hash() 导致播种/检索进程向量不一致（PYTHONHASHSEED 随机化）。"""
    from config import DATA
    code = ("import sys, os;sys.path.insert(0,%r);"
            "from stores.vector_store import search;"
            "print([x['case'] for x in search('泵振动持续变大怎么办',2)])" % ROOT)
    env = dict(os.environ, P77_DATA_DIR=DATA)
    outs = {subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                           capture_output=True, text=True).stdout for _ in range(3)}
    assert len(outs) == 1, "多次独立进程检索结果不一致 → 嵌入不可复现"


def test_todo_c4_empty_collection_boundary(tmp_path, monkeypatch):
    import stores.vector_store as vs
    monkeypatch.setattr(vs, "CHROMA_DIR", str(tmp_path / "empty"))
    monkeypatch.setattr(vs, "COLLECTION", "nothing_here")
    assert vs.search("随便查", 3) == []                      # 空库边界：返回空而非抛错


def test_todo_c4_ablation_bigram_beats_unigram(seeded):
    """消融对照：同一 gold 集上 bigram 嵌入 recall 不低于纯字级（eval_retrieval 的断言版）。"""
    from stores.vector_store import DIM, HashEmbedding, slot, unit
    from eval_retrieval import QUERIES, CASES

    def topk(ef, q, k):
        dv = [unit(list(map(float, v))) for v in ef([c["text"] for c in CASES])]
        qv = unit(list(map(float, ef([q])[0])))
        sims = [sum(a * b for a, b in zip(qv, d)) for d in dv]
        return sorted(range(len(sims)), key=lambda i: -sims[i])[:k]

    class Uni(HashEmbedding):
        def _embed(self, text):
            v = [0.0] * DIM
            for g in list(text):
                v[slot(g)] += 1.0
            return unit(v)

    def recall(ef, k=2):
        return sum(1 for q, gold in QUERIES
                   if any(CASES[i]["id"] in gold for i in topk(ef, q, k))) / len(QUERIES)

    uni, bi = recall(Uni()), recall(HashEmbedding())
    assert bi >= uni, f"bigram({bi}) 不应低于字级消融({uni})"
    assert bi >= 0.8, f"离线哈希嵌入在 gold 集上的实测下限为 0.857，跌破说明嵌入退化：{bi}"
    assert unit([0.0] * DIM) == [0.0] * DIM                  # 空输入：零向量不除零
    import zlib
    assert slot("振动") == zlib.crc32("振动".encode()) % DIM  # 异常：槽位必须与进程无关


# ------------------------------------------------------------------ 工单点位 P7-3/5（B 层）
def test_todo_b3_impact_path(seeded):
    from stores.graph import impact_path
    p = impact_path("PUMP-03")
    assert p["own_lines"] == ["LINE-A2"]
    assert p["collateral"][0]["downstream"] == "MOTOR-A2-1"
    assert "LINE-A2" in p["affected_lines"]


def test_todo_b3_unknown_device_boundary(seeded):
    from stores.graph import impact_path
    p = impact_path("GHOST-01")
    assert p["own_lines"] == [] and p["collateral"] == [] and p["affected_lines"] == []


def test_todo_b3_cypher_param_binding(seeded):
    """异常/注入边界：设备号里带引号不得改变 Cypher 语义（旧实现是 f-string 拼接）。"""
    from stores.graph import impact_path
    assert impact_path("PUMP-03' OR '1'='1")["collateral"] == []


def test_todo_b5_react_five_evidences(seeded):
    from agent.engineer import investigate
    r = investigate("PUMP-03振动持续变大，会影响哪些产线？以前怎么处理的？")
    assert set(r["evidence_tools"]) == {"query_relational", "query_timeseries",
                                        "impact_path", "semantic_search",
                                        "model_predict"}
    assert r["steps"] == len(r["trace"]) >= 6                # 5 取证 + 结案
    c = r["conclusion"]
    assert c["level"] in ("正常", "预警", "报警")
    assert c["suggest_action"] and c["prob_wear"] is not None
    assert set(c["evidence"]) == set(r["evidence_tools"])    # 有据可查（思政观测点）


def test_todo_b5_trace_records_thought_and_args(seeded):
    from agent.engineer import investigate
    r = investigate("FAN-02振动变大，影响哪些产线？以前怎么处理？")
    tool_steps = [t for t in r["trace"] if "obs" in t]
    assert all(t["thought"] and t["args"] for t in tool_steps)
    assert all(json.loads(t["obs"]) is not None for t in tool_steps)  # 全量 JSON 可解析


def test_todo_b5_long_observation_does_not_break():
    """回归：trace 只存 400 字截断串时，结案 json.loads 必炸（台账证据就超 400 字）。"""
    from agent.engineer import _conclude
    long_obs = json.dumps({"points": [{"tag": "t%02d" % i} for i in range(60)]})
    assert len(long_obs) > 400
    c = _conclude([{"step": 1, "act": "query_relational", "obs": long_obs}])
    assert c["evidence"]["query_relational"]["points"]


def test_todo_b5_empty_trace_boundary():
    from agent.engineer import _conclude
    c = _conclude([])                                        # 空输入：不抛，给保守结论
    assert c["level"] == "正常" and c["suggest_action"] == "加密监测"


def test_todo_b5_empty_question_boundary(seeded):
    from agent.engineer import investigate
    r = investigate("")
    assert r["steps"] >= 1 and r["conclusion"]["level"] == "正常"


def test_conclude_level_thresholds():
    """极值：预警/报警分档边界（0.4 / 0.7）。"""
    from agent.engineer import _conclude
    def mk(w):
        return _conclude([{"step": 1, "act": "model_predict",
                           "obs": json.dumps({"pred": {"proba_wear": w}})}])
    assert mk(0.4)["level"] == "正常"
    assert mk(0.41)["level"] == "预警"
    assert mk(0.7)["level"] == "预警"
    assert mk(0.71)["level"] == "报警"


def test_tools_cache_hit_miss(seeded):
    from agent import tools
    tools.KV.put("pred:CACHED-01", json.dumps({"proba_wear": 0.5}), ttl=30)
    assert tools.model_predict("CACHED-01")["cache"] == "HIT"   # TTL 内直接命中
    tools.KV.put("pred:NODATA-01", "not-json", ttl=-1)          # 过期写入→视为 MISS 路径
    assert tools.model_predict("NODATA-01")["pred"]["proba_wear"] is None  # 无采样不编分数


def test_tools_unknown_name_is_not_keyerror(seeded):
    from agent.tools import run_tool
    r = run_tool("no_such_tool", {})
    assert "error" in r and "available" in r


def test_kv_backends_and_ttl():
    from stores.kv import DiskKV, MemoryKV, RedisKV
    assert {RedisKV.name, DiskKV.name, MemoryKV.name} == {"redis", "diskcache", "memory"}
    kv = MemoryKV()
    kv.put("k", "v", ttl=1)
    assert kv.get("k") == "v" and kv.incr("c") == 1 and kv.incr("c") == 2
    kv.put("gone", "x", ttl=-1)
    time.sleep(0.01)
    assert kv.get("gone") is None                            # 极值：过期即不可见
    assert kv.get("never_written") is None                   # 空输入：未命中返回 None


def test_diskkv_incr_is_atomic_counter(tmp_path):
    diskcache = pytest.importorskip("diskcache")             # 异常路径：不静默降精度
    from stores.kv import DiskKV
    kv = DiskKV(str(tmp_path / "dc"))
    assert [kv.incr("hits", ttl=60) for _ in range(3)] == [1, 2, 3]


# ---------------------------------------------------------------- D 层：API 契约
@pytest.fixture(scope="session")
def client(seeded):
    mod = pytest.importorskip("litestar.testing")
    from service.app import app
    with mod.TestClient(app) as c:
        yield c


def test_tier_d_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["kv"] in ("redis", "diskcache", "memory")


def test_tier_d_device_live_then_cache(client):
    a = client.get("/api/device/FAN-02")
    b = client.get("/api/device/FAN-02")
    assert a.status_code == 200 and "LINE-B1" in json.dumps(a.json(), ensure_ascii=False)
    assert a.json()["source"] == "live" and b.json()["source"] == "cache"  # 连刷两次看差异


def test_tier_d_predict_and_agent(client):
    p = client.post("/api/predict", json={"device": "PUMP-03"})
    assert p.status_code == 200 and "proba_wear" in json.dumps(p.json())
    q = client.post("/api/agent/ask",
                    json={"question": "FAN-02振动变大，影响哪些产线？以前怎么处理？"},
                    headers={"x-client": "pytest"})
    assert q.status_code == 200 and q.json()["conclusion"]["suggest_action"]


def test_tier_d_error_paths_are_not_500(client):
    assert client.get("/api/device/NOPE-99").status_code == 404
    assert client.post("/api/agent/ask", json={"question": ""}).status_code == 400


def test_tier_d_rate_limit_uses_config(client):
    from config import RATE_LIMIT_PER_HOUR
    assert RATE_LIMIT_PER_HOUR > 0
    r = client.post("/api/agent/ask", json={"question": "台账"},
                    headers={"x-client": "rl-burst"})
    assert r.status_code == 200 and r.json()["rate_used"] >= 1


# ---------------------------------------------------------------- A 层：升级位
def test_tier_a_embedding_backend_switch_is_honest(seeded, capsys):
    from stores.vector_store import resolve_embedding
    ef, label = resolve_embedding("bge")                     # 缺依赖→回退且明确说明
    out = capsys.readouterr().out
    assert label.startswith("hash") or "bge-small-zh" in label
    if label.startswith("hash"):
        assert "回退" in out, "回退必须留痕，不许静默降级"


def test_tier_a_recall_eval_runs(seeded):
    from config import DATA
    env = dict(os.environ, P77_DATA_DIR=DATA)
    r = subprocess.run([sys.executable, "eval_retrieval.py", "--k", "2"],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]
    assert "recall@2" in r.stdout and "like" in r.stdout and "hash" in r.stdout


def test_tier_a_f1_gate_blocks_bad_model():
    """异常路径：门禁函数必须能判 False（不带病覆盖模型文件）。"""
    from train_model import MIN_F1, train
    import numpy as np
    rng = np.random.RandomState(0)
    X = rng.normal(0, 1, (200, 5))
    y = rng.binomial(1, 0.5, 200)                            # 纯噪声标签
    _, f1 = train(X, y)
    assert f1 < MIN_F1 or MIN_F1 <= 0.0                      # 噪声数据不该过门禁
