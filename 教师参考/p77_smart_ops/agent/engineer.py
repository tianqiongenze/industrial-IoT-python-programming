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
            trace.append({"step": step, "thought": msg["content"],
                          "act": name, "args": args,
                          "obs": json.dumps(obs, ensure_ascii=False)[:400]})
            messages.append({"role": "assistant", "content": msg["content"]})
            messages.append({"role": "user",
                             "content": f"工具{name}返回："
                                        + json.dumps(obs, ensure_ascii=False)[:800]})
    return {"question": question, "steps": len(trace),
            "trace": trace, "conclusion": _conclude(trace)}


def _conclude(trace=None) -> dict:
    """从取证轨迹提炼结构化结论（标签/依据/建议动作/波及面）"""
    obs = {t["act"]: t for t in trace if "obs" in t}
    pred = json.loads(obs["model_predict"]["obs"]) if "model_predict" in obs else {}
    wear = pred.get("pred", {}).get("proba_wear")
    cases = json.loads(obs["semantic_search"]["obs"]) if "semantic_search" in obs else []
    path = json.loads(obs["impact_path"]["obs"]) if "impact_path" in obs else {}
    level = "报警" if (wear or 0) > 0.7 else "预警" if (wear or 0) > 0.4 else "正常"
    return {
        "level": level,
        "prob_wear": wear,
        "suggest_action": cases[0]["meta"]["action"] if cases else "加密监测",
        "evidence": {k: json.loads(v["obs"]) for k, v in obs.items()},
        "collateral_lines": path.get("own_lines", []),
    }


if __name__ == "__main__":
    r = investigate("PUMP-03振动持续变大，会影响哪些产线？以前怎么处理的？")
    print(json.dumps(r["conclusion"], ensure_ascii=False, indent=1)[:600])
    print("…取证步数:", r["steps"])
