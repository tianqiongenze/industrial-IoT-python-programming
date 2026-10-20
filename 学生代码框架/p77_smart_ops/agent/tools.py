# -*- coding: utf-8 -*-
"""智能体工具箱：把5种存储+1个模型包成LLM可调用的function（OpenAI tools协议）

每个工具=存储引擎的一层薄封装：docstring即给LLM看的用途说明
"""
import json

from config import CLF_FILE

from stores import graph, kv, relational, timeseries, vector_store

KV = kv.make_kv()

TOOLS_SPEC = [
    {"type": "function", "function": {
        "name": "query_relational",
        "description": "查设备台账：名称/产线/测点/历史告警",
        "parameters": {"type": "object",
                       "properties": {"device": {"type": "string"}},
                       "required": ["device"]}}},
    {"type": "function", "function": {
        "name": "query_timeseries",
        "description": "查设备最近N分钟时序特征：均值/峰值/斜率/最新值",
        "parameters": {"type": "object",
                       "properties": {"device": {"type": "string"},
                                      "minutes": {"type": "integer"}},
                       "required": ["device"]}}},
    {"type": "function", "function": {
        "name": "impact_path",
        "description": "图数据库影响路径：设备异常波及哪些下游设备与产线",
        "parameters": {"type": "object",
                       "properties": {"device": {"type": "string"}},
                       "required": ["device"]}}},
    {"type": "function", "function": {
        "name": "semantic_search",
        "description": "向量库语义检索历史故障案例与处置动作",
        "parameters": {"type": "object",
                       "properties": {"query": {"type": "string"}},
                       "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "model_predict",
        "description": "诊断模型推理：时序特征→正常/磨损概率（结果写缓存）",
        "parameters": {"type": "object",
                       "properties": {"device": {"type": "string"}},
                       "required": ["device"]}}},
]


def model_predict(device: str) -> dict:
    """缓存优先的模型推理：同设备10秒内重复问直接命中KV（演示缓存价值）"""
    ck = f"pred:{device}"
    hit = KV.get(ck)
    if hit:
        return {"device": device, "pred": json.loads(hit), "cache": "HIT"}
    feats = timeseries.window_feats(device)
    import joblib
    import numpy as np
    clf = joblib.load(CLF_FILE)
    x = np.array([[feats["avg_vib"], feats["max_vib"], feats["slope"],
                   feats["last_vib"], feats["samples"] / 100.0]])
    proba = clf.predict_proba(x)[0].tolist()
    out = {"label": int(proba[1] > 0.5), "proba_wear": round(proba[1], 3),
           "feats": feats}
    KV.put(ck, json.dumps(out, ensure_ascii=False), ttl=10)
    return {"device": device, "pred": out, "cache": "MISS"}


REGISTRY = {
    "query_relational": lambda a: relational.device_profile(a["device"]),
    "query_timeseries": lambda a: timeseries.window_feats(a["device"], a.get("minutes", 10)),
    "impact_path": lambda a: graph.impact_path(a["device"]),
    "semantic_search": lambda a: vector_store.search(a["query"], 2),
    "model_predict": lambda a: model_predict(a["device"]),
}


def run_tool(name: str, arguments: dict) -> dict:
    return REGISTRY[name](arguments)


if __name__ == "__main__":
    print(json.dumps(run_tool("query_timeseries", {"device": "PUMP-03"}),
                     ensure_ascii=False))
