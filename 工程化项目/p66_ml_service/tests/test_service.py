# -*- coding: utf-8 -*-
"""推理服务活体测试：线程起服（port=0 内核临时端口）+ 真实 HTTP 请求/响应。"""
import json
import threading
import urllib.error
import urllib.request

import pytest

from ml_service import data, service


@pytest.fixture(scope="module")
def live_server():
    from ml_service import core
    X, y = data.make_synthetic(200, seed=5)
    model, _ev = core.evaluate(X, y, seed=5)
    srv = service.create_server(model, "test-model.joblib", data.N_DIM,
                                host="127.0.0.1", port=0)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    yield base, srv
    srv.shutdown()
    srv.server_close()
    th.join(timeout=5)


def _request(url, data_bytes=None):
    req = urllib.request.Request(url, data=data_bytes,
                                 headers={"Content-Type": "application/json"}
                                 if data_bytes else {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _get(url):
    return _request(url)


def _post(url, payload_bytes):
    return _request(url, payload_bytes)


def test_health_real_inference(live_server):
    base, _srv = live_server
    status, body = _get(base + "/health")
    assert status == 200
    assert body["status"] == "ok" and body["model"] == "test-model.joblib"
    assert body["n_features"] == 30 and body["probe_predict"] in (0, 1)


def test_predict_valid_request_response(live_server):
    base, _srv = live_server
    feats = [0.1 * i for i in range(30)]
    status, body = _post(base + "/predict", json.dumps({"features": feats}).encode())
    assert status == 200
    assert body["prediction"] in (0, 1)
    assert body["label"] in ("正常", "磨损")
    assert 0.0 <= body["proba_wear"] <= 1.0
    assert body["model"] == "test-model.joblib"


def test_predict_wrong_dimension_400(live_server):
    base, _srv = live_server
    status, body = _post(base + "/predict",
                         json.dumps({"features": [1.0] * 29}).encode())
    assert status == 400 and "30" in body["detail"]


def test_predict_malformed_json_400(live_server):
    base, _srv = live_server
    status, body = _post(base + "/predict", b"{not-json")
    assert status == 400 and body["error"] == "bad request"
    status, body = _post(base + "/predict", json.dumps({"nope": 1}).encode())
    assert status == 400                       # 缺 features 键
    status, body = _post(base + "/predict",
                         json.dumps({"features": ["a"] * 30}).encode())
    assert status == 400                       # 非数值特征


def test_unknown_path_404(live_server):
    base, _srv = live_server
    status, body = _get(base + "/nope")
    assert status == 404 and "/predict" in body["routes"]
    status, body = _post(base + "/other", b"{}")
    assert status == 404


def test_server_stats_accumulate(live_server):
    base, srv = live_server
    assert srv.stats["count"] > 0 and all(x >= 0 for x in srv.stats["latencies_ms"])


def test_bench_returns_real_latency_stats(live_server):
    """B层压测：真实 HTTP 往返，warmup+100 次请求，验收口径 p95。"""
    _base, _srv = live_server
    from ml_service import core
    X, y = data.make_synthetic(120, seed=6)
    model, _ev = core.evaluate(X, y, seed=6)
    res = service.bench(model, data.N_DIM, n_requests=40, warmup=5,
                       features=[[float(v) for v in row] for row in X[:8]])
    for key in ("warmup_first_ms", "mean_ms", "p50_ms", "p95_ms", "p99_ms",
                "max_ms", "qps"):
        assert isinstance(res[key], float) and res[key] > 0
    assert res["p95_ms"] >= res["p50_ms"]
    assert res["n_requests"] == 40
