# -*- coding: utf-8 -*-
"""LLM客户端：离线规则引擎（默认） ⇄ 真实OpenAI兼容服务（设OPENAI_BASE_URL即切）

返回统一为OpenAI chat.completions形状：
  {"choices":[{"message":{"role":"assistant","content":..., "tool_calls":[...]}}]}
工单思政点：企业数据不出域——默认全离线；接真实API时数据脱敏前置。
"""
import json
import re

from config import LLM_MODEL, OPENAI_BASE_URL


def chat(messages: list, tools: list = None) -> dict:
    if OPENAI_BASE_URL:
        return _chat_remote(messages, tools)
    return _chat_local(messages, tools)


def _chat_remote(messages, tools):
    import urllib.request
    body = json.dumps({"model": LLM_MODEL, "messages": messages,
                       "tools": tools or [], "temperature": 0.2}).encode()
    req = urllib.request.Request(
        OPENAI_BASE_URL.rstrip("/") + "/chat/completions", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _chat_local(messages, tools):
    """规则引擎：解析问题关键词 → 产出下一步tool_call 或最终诊断结论文本
    （教学语义：让ReAct循环在没有GPU/外网的机房也能完整跑通）"""
    user_msgs = [m["content"] for m in messages
                 if m.get("role") == "user" and not str(m.get("content", "")).startswith("工具")]
    q = user_msgs[0] if user_msgs else ""          # 空问题边界：旧写法 next() 直接 StopIteration
    plan = _plan(q)
    used = _used(messages)
    nxt = next((t["function"]["name"] for t in plan if t["function"]["name"] not in used), None)
    if nxt and tools:
        spec = next(t for t in tools if t["function"]["name"] == nxt)
        args = _bind_args(nxt, q, spec)
        return {"choices": [{"message": {
            "role": "assistant", "content": f"调用工具 {nxt}",
            "tool_calls": [{"id": f"call_{nxt}", "type": "function",
                            "function": {"name": nxt, "arguments": args}}]}}]}
    return {"choices": [{"message": {
        "role": "assistant",
        "content": "已收集全部证据，输出诊断工单（见最终结构化结果）。"}}]}


DEV_RE = re.compile(r"PUMP-\d+|FAN-\d+|MOTOR-[A-Z0-9-]+")


def _plan(q: str) -> list:
    p = []
    # 工单验收口径要求"五步取证"（台账→时序→图谱→案例→模型）：
    # 只要问题里点名了设备，台账永远是第一手证据，必须进计划
    if DEV_RE.search(q) or re.search(r"台账|设备|测点|告警|参数", q):
        p.append({"function": {"name": "query_relational"}})
    if re.search(r"振动|趋势|最近|时序|窗口", q):
        p.append({"function": {"name": "query_timeseries"}})
    if re.search(r"影响|波及|联动|停产|停线|路径", q):
        p.append({"function": {"name": "impact_path"}})
    if re.search(r"案例|经验|类似|以前|怎么处理", q):
        p.append({"function": {"name": "semantic_search"}})
    p.append({"function": {"name": "model_predict"}})
    return p or [{"function": {"name": "query_relational"}}]


def _bind_args(name, q, spec):
    m = DEV_RE.search(q)
    dev = m.group(0) if m else "PUMP-03"
    props = spec["function"]["parameters"]["properties"]
    return json.dumps({k: (dev if k == "device" else
                           (q[:60] if k == "query" else 10))
                       for k in props}, ensure_ascii=False)


def _used(messages):
    out = []
    for m in messages:
        c = m.get("content", "")
        if isinstance(c, str) and c.startswith("调用工具 "):
            out.append(c[5:])
    return out
