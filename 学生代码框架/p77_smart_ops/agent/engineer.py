# -*- coding: utf-8 -*-
# [教学脚手架] 下列导入/变量供 TODO 完成后使用，故标注 noqa 而非删除
"""运维智能体（ReAct循环）：思考→选工具→观察→…→结论

角色设定：两江智造集团"值班工程师小郑"——
  收到问题 → 依次取证（台账/时序/图谱/案例/模型）→ 汇总为结构化诊断工单
上限8步防死循环；每步留痕（可解释性=工单思政"有据可查"）
"""
import json

from agent import llm, tools  # noqa: F401

SYSTEM = ("你是两江智造集团设备智能运维中心的值班工程师。"
          "收到设备问题后，按需调用工具取证：台账→时序→影响路径→相似案例→模型诊断，"
          "最后输出结论。不编造数据，只用工具返回的证据。")
MAX_STEPS = 8


def investigate(question: str) -> dict:
    messages = [{"role": "system", "content": SYSTEM},  # noqa: F841
                {"role": "user", "content": question}]
    trace = []
    for step in range(1, MAX_STEPS + 1):
        # TODO-P7-5: ReAct循环——llm.chat()取tool_calls → tools.run_tool(name, args)
        #   → 观察结果append进messages（"工具{name}返回：..."）→ 无tool_calls即break
        #   每步 append {"step","thought","act","args","obs"} 到 trace
        break
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
