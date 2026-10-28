# -*- coding: utf-8 -*-
"""P6.2 推理服务：标准库 http.server.ThreadingHTTPServer 实现 POST /predict + GET /health。

工单口径与诚实声明：
  * /health 做「真推理一发」——进程活着≠模型可用（工程化要求2）；
  * 参数错/维度不符/非 JSON 一律 400（JSON 错误体），未知路径 404；
  * http.server 单线程阻塞问题：ThreadingHTTPServer 已按连接起线程，教学演示
    足够；生产应换 ASGI（Litestar/Granian）——决策矩阵见 docs/03 与报告；
  * bench() 为真实 HTTP 压测：warmup 后发 n 次请求，报 mean/p50/p95/p99/QPS
    （验收看 p95 不看均值，工程化要求3）。
"""
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import sklearn

log = logging.getLogger("p66.infer")


def _json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def create_server(model, model_name, n_features, host="127.0.0.1", port=0,
                  feature_names=None):
    """构建（不启动）推理服务；port=0 时由内核分配临时端口（测试用）。"""
    lock = threading.Lock()  # sklearn predict 并发保护（教学演示够用）

    class Handler(BaseHTTPRequestHandler):
        server_version = "p66-ml-service/2.0"

        def _send(self, code, payload):
            body = _json_bytes(payload)
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                try:
                    dummy = [[0.0] * n_features]
                    with lock:
                        probe = int(model.predict(dummy)[0])      # 真推理一发
                    self._send(200, {"status": "ok", "model": model_name,
                                     "n_features": n_features,
                                     "sklearn": sklearn.__version__,
                                     "probe_predict": probe})
                except Exception as exc:                          # 模型坏→503
                    log.exception("health 自检失败")
                    self._send(503, {"status": "unhealthy", "error": str(exc)})
            else:
                self._send(404, {"error": "not found", "routes": ["/health", "/predict"]})

        def do_POST(self):
            t0 = time.perf_counter()
            code = 400
            try:
                if self.path != "/predict":
                    self._send(404, {"error": "not found", "routes": ["/predict"]})
                    return
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                feats = body["features"]
                if not isinstance(feats, list):
                    raise ValueError("features 必须是数组")
                if len(feats) != n_features:
                    raise ValueError("特征维度 %d 与模型契约 %d 不符"
                                     % (len(feats), n_features))
                arr = np.asarray(feats, dtype=float)
                if not np.all(np.isfinite(arr)):
                    raise ValueError("特征含 NaN/Inf")
                with lock:
                    pred = int(model.predict([feats])[0])
                    proba = (float(model.predict_proba([feats])[0][1])
                             if hasattr(model, "predict_proba") else None)
                code = 200
                self._send(200, {"prediction": pred,
                                 "label": "磨损" if pred else "正常",
                                 "proba_wear": None if proba is None else round(proba, 4),
                                 "model": model_name})
            except Exception as exc:
                log.warning("请求被拒绝: %s", exc)
                self._send(code, {"error": "bad request", "detail": str(exc)[:200],
                                  "hint": '需 JSON: {"features": [%d 个数值]}' % n_features})
            finally:
                ms = (time.perf_counter() - t0) * 1000.0
                self.server.stats["count"] += 1
                self.server.stats["latencies_ms"].append(round(ms, 4))

        def log_message(self, fmt, *args):   # 优雅落日志（默认 stderr→logging）
            log.info("%s %s", self.address_string(), fmt % args)

    srv = ThreadingHTTPServer((host, port), Handler)
    srv.stats = {"count": 0, "latencies_ms": []}
    srv.model_name = model_name
    return srv


def serve_forever(cfg, model_path=None):
    """CLI --serve 入口：按配置端口起服务并阻塞（Ctrl-C 优雅退出）。"""
    import os
    import joblib
    from . import core
    path = model_path or os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "output",
        str(cfg.raw.get("model_name", "model_v1.joblib")))
    model = core.load_model(path)
    port = int(cfg.raw.get("port", 8899))
    host = str(cfg.raw.get("host", "127.0.0.1"))
    srv = create_server(model, os.path.basename(path), int(cfg.raw.get("n_features", 30)),
                        host=host, port=port)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    print("推理服务已启动: http://%s:%d/predict （POST 30维特征；GET /health 自检）"
          % (host, srv.server_address[1]), flush=True)
    print("安全提示: 默认仅监听 127.0.0.1；改 host=0.0.0.0 仅供机房局域网教学，切勿暴露公网",
          flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("收到 Ctrl-C，正在优雅停机…", flush=True)
    finally:
        srv.server_close()
        print("服务已停止，共处理 %d 个请求" % srv.stats["count"], flush=True)


def bench(model, n_features, n_requests=100, warmup=5, features=None,
          host="127.0.0.1"):
    """真实 HTTP 压测：起临时端口服务→warmup→n 次 POST /predict 计时。

    返回 warmup/mean/p50/p95/p99/max/QPS；两次运行耗时数字会抖动，
    故流水线默认把结果固化在 output/bench.json 缓存（--bench 强制重测）。
    """
    import urllib.request

    if features is None:
        features = [[0.0] * n_features]
    srv = create_server(model, "bench-temp", n_features, host=host, port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    url = "http://%s:%d/predict" % (host, srv.server_address[1])
    payloads = []
    for i in range(max(n_requests, warmup) + 1):
        row = features[i % len(features)]
        payloads.append(_json_bytes({"features": row}))

    def _one(body):
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()

    lat = []
    sent = 0
    t0 = time.perf_counter()
    _one(payloads[0])
    sent += 1
    warmup_ms = (time.perf_counter() - t0) * 1000.0
    for i in range(1, warmup):
        _one(payloads[i % len(payloads)])      # 预热后续请求不单独计时
        sent += 1
    start = time.perf_counter()
    for i in range(n_requests):
        t1 = time.perf_counter()
        _one(payloads[(warmup + i) % len(payloads)])
        lat.append((time.perf_counter() - t1) * 1000.0)
        sent += 1
    total = time.perf_counter() - start
    recorded = len(srv.stats["latencies_ms"])   # 服务端也逐条留了延迟记录
    srv.shutdown()
    srv.server_close()
    thread.join(timeout=5)
    arr = np.asarray(lat)
    return {
        "n_requests": n_requests, "warmup": warmup,
        "warmup_first_ms": round(float(warmup_ms), 3),
        "mean_ms": round(float(arr.mean()), 3),
        "p50_ms": round(float(np.percentile(arr, 50)), 3),
        "p95_ms": round(float(np.percentile(arr, 95)), 3),
        "p99_ms": round(float(np.percentile(arr, 99)), 3),
        "max_ms": round(float(arr.max()), 3),
        "qps": round(n_requests / total, 1),
        # 工单良好(C)「延迟记录完整」的可查账口径：客户端计时条数 == 服务端记录条数
        "client_timed": len(lat), "requests_sent": sent,
        "server_recorded": recorded, "records_match": bool(recorded == sent),
        "note": "真实 HTTP 往返计时（本机临时端口，单并发顺序压测；"
                "验收口径看 p95 不看均值）",
    }


# 工单《P6 验收标准》优秀(B)「服务异常处理(404/参数错)」的逐条取证清单：
# (探针名, 方法, 路径, 请求体代号, 期望状态码)。清单外置到 config 的 error_probes，
# 少配一条就少一条证据、判档随之翻红——判定权在配置，不在代码文案里。
ERROR_PROBES = (
    ("health_get", "GET", "/health", None, 200),
    ("predict_ok", "POST", "/predict", "ok", 200),
    ("predict_non_json", "POST", "/predict", "raw", 400),
    ("predict_missing_features", "POST", "/predict", "empty_obj", 400),
    ("predict_wrong_dim", "POST", "/predict", "wrong_dim", 400),
    ("predict_nan", "POST", "/predict", "nan", 400),
    ("unknown_get", "GET", "/nope", None, 404),
    ("unknown_post", "POST", "/nope", "ok", 404),
)


def error_selftest(model, n_features, host="127.0.0.1", probes=None):
    """起临时端口真打 8 类请求，逐条比对 200/400/404 是否按契约返回。

    只测 happy path 的服务等于没测异常分支：这里把工单优秀(B) 要求的两类
    错误码（未知路径 404、参数错 400）打成可核对的清单，含请求方法、路径、
    期望码与实到码，逐条留证。
    """
    import urllib.error
    import urllib.request

    if probes is None:
        probes = list(ERROR_PROBES)
    srv = create_server(model, "probe-temp", n_features, host=host, port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base = "http://%s:%d" % (host, srv.server_address[1])
    bodies = {
        "ok": _json_bytes({"features": [0.0] * n_features}),
        "wrong_dim": _json_bytes({"features": [0.0] * (n_features + 3)}),
        "nan": _json_bytes({"features": [float("nan")] * n_features}),
        "empty_obj": _json_bytes({}),
        "raw": b"this-is-not-json",
    }
    rows = []
    try:
        for name, method, path, body_key, expect in probes:
            data = None if body_key is None else bodies[body_key]
            req = urllib.request.Request(
                base + path, data=data, method=method,
                headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    got = int(resp.status)
            except urllib.error.HTTPError as exc:
                got = int(exc.code)
            rows.append({"probe": name, "method": method, "path": path,
                         "expect": int(expect), "got": got,
                         "ok": got == int(expect)})
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)
    return {
        "probes": rows, "n_probes": len(rows),
        "n_ok": sum(1 for r in rows if r["ok"]),
        "all_ok": bool(rows) and all(r["ok"] for r in rows),
        "codes_seen": sorted({r["got"] for r in rows}),
        "error_cases_ok": sum(1 for r in rows
                              if r["expect"] in (400, 404) and r["ok"]),
        "note": "进程内临时端口，逐条真实 HTTP 往返（不依赖已安装的 Web 框架）",
    }
