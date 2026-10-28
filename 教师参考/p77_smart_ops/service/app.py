# -*- coding: utf-8 -*-
"""P7 平台服务层：Litestar（全异步）+ Granian（Rust运行时，高吞吐）

为什么换掉 http.server / 传统同步框架（工单P7决策矩阵）：
  http.server单线程阻塞  →  Litestar原生async并发
  uvicorn(纯Python事件环) →  granian(Rust多运行时,--workers N 直接拉满)
启动: granian --interface asgi "service.app:app" --host 127.0.0.1 --port 8900
  （机房验证: ab -n 2000 -c 50 对比 http.server 与 granian 的QPS差一个数量级）

处理器签名要点（工单"常见错误速查"第5条，踩过才写得出）：
  · 返回值**必须**有类型注解，否则路由注册即抛 ImproperlyConfiguredException；
  · 错误路径用 HTTPException（404/400/429），不要返回 None 或裸 dict——
    否则"设备不存在"这种正常业务分支会把异常吞成 500，运维端根本分不清是崩了还是真没数据；
  · D 层验收口径是"4 个 API 全部 200"，而 Litestar 的 POST 默认返回 **201**，
    必须显式 status_code=200 压平，否则 curl -w '%{http_code}' 一测就红；
  · 路径参数用 `FromPath[str]` 声明：Litestar 2.24 对"路径写 {code:str}、签名只写
    code: str"的**推断式风格**发 LitestarDeprecationWarning（启动日志一刷就是），
    而路径串里的 `:str` 仍是硬性要求——两处口径都要写对，OpenAPI 才拿得到 schema。
"""
import json
from typing import Any, Dict

from litestar import Litestar, Request, get, post
from litestar.exceptions import HTTPException
from litestar.params import FromPath

from agent import engineer, tools
from config import CACHE_TTL_DEV, RATE_LIMIT_PER_HOUR
from stores import kv, relational, timeseries

KV = kv.make_kv()


@get("/health")
async def health() -> dict:
    return {"ok": True, "kv": KV.name, "svc": "smart-ops", "ver": "1.0"}


@get("/api/device/{code:str}")
async def device(code: FromPath[str]) -> Dict[str, Any]:
    """设备360°视图：关系台账 + 时序特征（TTL 外置，扛住大屏轮询）

    查无设备→404。旧写法把 {"error":...} 和时序特征拼一起，
    window_feats 在 DuckDB 上抛 BinderException，客户端只收到 500。
    """
    prof = relational.device_profile(code)
    if prof.get("error"):
        raise HTTPException(status_code=404, detail=prof["error"])
    ck = f"dev:{code}"
    cached = KV.get(ck)
    if cached:
        return {"source": "cache", "data": json.loads(cached)}
    data = {**prof, "ts_feats": timeseries.window_feats(code)}
    KV.put(ck, json.dumps(data, ensure_ascii=False), ttl=CACHE_TTL_DEV)
    return {"source": "live", "data": data}


@post("/api/predict", status_code=200)
async def predict(data: dict) -> dict:
    """模型推理（缓存 MISS→HIT 可见）——body: {"device": "PUMP-03"}"""
    return tools.model_predict(data.get("device", "PUMP-03"))


@post("/api/agent/ask", status_code=200)
async def ask(request: Request) -> Dict[str, Any]:
    """智能体问询（限流：每调用方每小时 RATE_LIMIT_PER_HOUR 次，计数留痕）"""
    body = await request.json()
    q = (body.get("question") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="question 不能为空")
    who = (request.headers.get("x-client") or "anon")[:32]
    n = KV.incr(f"rl:{who}", ttl=3600)
    if n > RATE_LIMIT_PER_HOUR:
        raise HTTPException(status_code=429,
                            detail=f"限流：{n}>{RATE_LIMIT_PER_HOUR} 次/小时")
    r = engineer.investigate(q)
    r["rate_used"] = n
    return r


app = Litestar([health, device, predict, ask], logging_config=None)
