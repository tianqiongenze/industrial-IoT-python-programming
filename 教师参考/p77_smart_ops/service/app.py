# -*- coding: utf-8 -*-
"""P7 平台服务层：Litestar（全异步）+ Granian（Rust运行时，高吞吐）

为什么换掉 http.server / 传统同步框架（工单P7决策矩阵）：
  http.server单线程阻塞  →  Litestar原生async并发
  uvicorn(纯Python事件环) →  granian(Rust多运行时,--workers N 直接拉满)
启动: granian --interface asgi "service.app:app" --host 127.0.0.1 --port 8900
  （机房验证: ab -n 2000 -c 50 对比 http.server 与 granian 的QPS差一个数量级）
"""
import json

from litestar import Litestar, Request, Response, get, post

from agent import engineer, tools
from stores import kv, relational, timeseries

KV = kv.make_kv()


@get("/health", sync_to_thread=False)
async def health() -> dict:
    return {"ok": True, "kv": KV.name, "svc": "smart-ops", "ver": "1.0"}


@get("/api/device/{code:str}")
async def device(code: str) -> dict:
    """设备360°视图：关系台账 + 时序特征（缓存10s，扛住大屏轮询）"""
    ck = f"dev:{code}"
    if KV.get(ck):
        return {"source": "cache", "data": json.loads(KV.get(ck))}
    data = {**relational.device_profile(code),
            "ts_feats": timeseries.window_feats(code)}
    KV.put(ck, json.dumps(data, ensure_ascii=False), ttl=10)
    return {"source": "live", "data": data}


@post("/api/predict")
async def predict(data: dict) -> dict:
    """模型推理（缓存10s）——body: {"device": "PUMP-03"}"""
    return tools.model_predict(data.get("device", "PUMP-03"))


@post("/api/agent/ask")
async def ask(request: Request) -> dict:
    """智能体问询（限流：每调用方每小时60次，计数留痕）"""
    body = await request.json()
    q = body.get("question", "")
    who = (request.headers.get("x-client") or "anon")[:32]
    n = KV.incr(f"rl:{who}")
    if n > 60:
        return Response({"error": "rate limited", "n": n}, status_code=429)
    r = engineer.investigate(q)
    r["rate_used"] = n
    return r


app = Litestar([health, device, predict, ask], logging_config=None)
