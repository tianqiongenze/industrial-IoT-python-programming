# -*- coding: utf-8 -*-
"""运维智能体（ReAct循环）：思考→选工具→观察→…→结论

角色设定：两江智造集团"值班工程师小郑"——
  收到问题 → 依次取证（台账/时序/图谱/案例/模型）→ 汇总为结构化诊断工单
上限8步防死循环；每步留痕（可解释性=工单思政"有据可查"）
"""
import json

from agent import llm, tools

SYSTEM = ("你是两江智造集团设备智能运维中心的值班工程师。"
          "收到设备问题后，按需调用工具取证：台账→时序→影响路径→相似案例→模型诊断，"
          "最后输出结论。不编造数据，只用工具返回的证据。")
MAX_STEPS = 8


def investigate(question: str) -> dict:
    """工单点位 P7-5 答案：ReAct 循环——思考(llm.chat)→行动(run_tool)→观察(回灌消息)→…→结论

    两个易踩的实现坑（教师版已处理）：
      1. 回灌给 LLM 的观察值要截断（省上下文），但 trace 里必须留**全量 JSON**——
         只存截断串会让 _conclude 里 json.loads 直接抛错（>400字符的证据必炸）；
      2. MAX_STEPS 用尽仍未收敛时要显式落一步"步数上限"，否则 trace 与 steps 口径不一致。
    """
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": question}]
    trace = []
    for step in range(1, MAX_STEPS + 1):
        resp = llm.chat(messages, tools=tools.TOOLS_SPEC)
        msg = resp["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            trace.append({"step": step, "thought": msg["content"], "act": "结论"})
            break
        for c in calls:
            name = c["function"]["name"]
            args = json.loads(c["function"]["arguments"])
            obs = tools.run_tool(name, args)
            raw = json.dumps(obs, ensure_ascii=False)
            trace.append({"step": step, "thought": msg["content"],
                          "act": name, "args": args, "obs": raw,
                          "obs_preview": raw[:400]})
            messages.append({"role": "assistant", "content": msg["content"]})
            messages.append({"role": "user",
                             "content": f"工具{name}返回：" + raw[:800]})
    else:                                            # for 正常跑完=步数耗尽仍未收敛
        trace.append({"step": MAX_STEPS + 1, "thought": "达到步数上限，按已有证据结案",
                      "act": "结论"})
    return {"question": question, "steps": len(trace),
            "evidence_tools": sorted({t["act"] for t in trace if "obs" in t}),
            "trace": trace, "conclusion": _conclude(trace)}


def _load(s):
    """观察值安全反序列化：截断/非法 JSON 不炸结案，返回 None 并保留原串线索。"""
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return None


def _conclude(trace=None) -> dict:
    """从取证轨迹提炼结构化结论（标签/依据/建议动作/波及面）"""
    trace = trace or []
    obs = {t["act"]: t for t in trace if "obs" in t}
    pred = _load(obs["model_predict"]["obs"]) if "model_predict" in obs else {}
    pred = pred or {}
    wear = (pred.get("pred") or {}).get("proba_wear")
    cases = _load(obs["semantic_search"]["obs"]) if "semantic_search" in obs else []
    cases = cases or []
    path = _load(obs["impact_path"]["obs"]) if "impact_path" in obs else {}
    path = path or {}
    level = "报警" if (wear or 0) > 0.7 else "预警" if (wear or 0) > 0.4 else "正常"
    return {
        "level": level,
        "prob_wear": wear,
        "suggest_action": (cases[0]["meta"].get("action") if cases
                           and isinstance(cases[0].get("meta"), dict) else "加密监测"),
        "evidence": {k: _load(v["obs"]) for k, v in obs.items()},
        "affected_lines": path.get("affected_lines", path.get("own_lines", [])),
        "collateral_lines": path.get("own_lines", []),
    }


if __name__ == "__main__":
    for q in ("PUMP-03振动持续变大，会影响哪些产线？以前怎么处理的？",
              "FAN-02振动变大，影响哪些产线？以前怎么处理的？"):
        r = investigate(q)
        print(json.dumps(r["conclusion"], ensure_ascii=False, indent=1)[:600])
        print("取证步数:", r["steps"], "| 证据工具:", r["evidence_tools"])
