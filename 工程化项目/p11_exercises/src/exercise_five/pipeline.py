# -*- coding: utf-8 -*-
"""五题闯关流水线：load → 造样例 → 逐题执行 → 内置断言 → 规范度量
→ 工单分层达标（及格D/良好C/优秀B/超优A，另附保底自检）→ 迁移笔记
→ 报告/JSON 落盘。

只做编排与落盘，业务判定全部在 core/exercises/selfcheck 里。
"""
import os

from . import (core, exercises, io_utils, notes, report, selfcheck,
               stylecheck, testmap)

NOTES_RELPATH = os.path.join("docs", "09-C转Python迁移笔记.md")
SAMPLES_DIR = "samples"


def prepare_samples(cfg, out_dir):
    """按配置在 output/samples/ 下造题5 需要的样例文件（幂等、确定性）。"""
    reader_cfg = cfg.reader
    base = os.path.join(out_dir, SAMPLES_DIR)
    paths = {
        "sample": os.path.join(base, str(reader_cfg["sample_name"])),
        "bad": os.path.join(base, str(reader_cfg["bad_encoding_name"])),
        "missing": os.path.join(base, str(reader_cfg["missing_name"])),
        "empty": os.path.join(base, "empty.txt"),
        "large": os.path.join(base, "large.txt"),
        "dir": os.path.join(base, "dir_demo"),
    }
    io_utils.ensure_dir(base)
    io_utils.ensure_dir(paths["dir"])
    io_utils.write_text(paths["sample"], str(reader_cfg["sample_text"]))
    bad_bytes = bytes(int(b) & 0xFF for b in reader_cfg.get("bad_bytes", []))
    io_utils.write_bytes(paths["bad"], bad_bytes)
    io_utils.write_text(paths["empty"], "")
    lines = ["第%d行,温度=%.1f" % (i, i * 0.5) for i in range(1, 201)]
    paths["large_lines"] = len(lines)
    io_utils.write_text(paths["large"], "\n".join(lines) + "\n")
    if os.path.exists(paths["missing"]):
        os.remove(paths["missing"])
    return paths


def run(cfg, out_dir, root, tier=None, want_notes=True):
    """执行全流程，返回 (sections, result_dict)。"""
    os.makedirs(out_dir, exist_ok=True)
    files = prepare_samples(cfg, out_dir)

    runs = [exercises.exercise1(cfg), exercises.exercise2(cfg),
            exercises.exercise3(cfg), exercises.exercise4(cfg),
            exercises.exercise5(cfg, files)]

    cases = selfcheck.build_cases(cfg, files)
    results = selfcheck.run_cases(cases)
    summary = selfcheck.summarise(results)
    style = stylecheck.summarize(root)
    style["question_tests"] = testmap.count_per_question(
        os.path.join(root, "tests"))
    tools = stylecheck.probe()
    pylint = stylecheck.pylint_score(["src", "run.py"]) if tools[
        "pylint"]["available"] else {"available": False, "score": None,
                                     "note": tools["pylint"]["reason"],
                                     "output": ""}
    notes_path = os.path.join(root, NOTES_RELPATH)
    notes_info = {"entries": 0, "explain": "", "seed": cfg.seed,
                  "path": NOTES_RELPATH.replace(os.sep, "/"),
                  "abs_path": notes_path, "pass": False,
                  "required": notes.ENTRY_COUNT_REQUIRED, "skipped": True,
                  "verified_entries": 0, "questions_covered": 0,
                  "sections_complete": False}
    if want_notes:
        text, notes_info = notes.write(cfg, style, notes_path)
        io_utils.write_text(notes_path, text)
        notes_info["abs_path"] = notes_path
        notes_info["path"] = NOTES_RELPATH.replace(os.sep, "/")
        notes_info["chars"] = len(text)
        notes_info["skipped"] = False
    notes_info["exists"] = os.path.exists(notes_path)
    gates = selfcheck.tier_gate(results, summary, style, notes_info, cfg)
    chosen = (str(tier or cfg.meta.get("tier", "A"))).upper()

    result = {"work_order": cfg.meta.get("work_order", "P1.1"),
              "parser": cfg.parser, "config_warnings": cfg.warnings,
              "tier_requested": chosen,
              "exercises": {r["number"]: {"title": r["title"],
                                          "lines": r["lines"],
                                          "payload": r["payload"],
                                          "verdict": "PASS" if summary.get(
                                              r["number"], {}).get("pass")
                                          else "FAIL"} for r in runs},
              "selfcheck": summary, "tier_gates": gates,
              "tiers": gates["tiers"], "style": {
                  k: v for k, v in style.items() if k != "violations"},
              "style_violations": style["violations"][:20],
              "tools": tools, "pylint": {k: v for k, v in pylint.items()
                                         if k != "output"},
              "notes": notes_info, "samples": {k: v for k, v in files.items()
                                               if isinstance(v, str)}}

    sections = [("输入口径", ["解析器: %s｜配置告警: %s" % (
        cfg.parser, "; ".join(cfg.warnings) or "无"),
        "阈值: warn=%.1f danger=%.1f｜topk=%d｜seed=%d｜设备 %d 台（ID 宽度 %s）"
        "｜PEP 8 线: 及格D %.1f%% / 优秀B %.1f%%｜题数线: D≥%d C≥%d B≥%d"
        "｜命名有意义线 %.1f%%｜每题 pytest 用例线 ≥%d"
        % (cfg.warn, cfg.danger, cfg.topk, cfg.seed, len(cfg.device_rows),
           cfg.devices["id_width"], cfg.pep8_pass_rate_d,
           cfg.pep8_pass_rate_b, cfg.d_min_correct, cfg.c_min_correct,
           cfg.b_min_correct, cfg.naming_meaningful_rate,
           cfg.tests_per_question_min)]),
        ("逐题结果", _exercise_lines(runs)),
        ("内置断言（每题 正常/空输入/极值/异常）", _assertion_lines(results,
                                                                summary)),
        ("分层达标（工单口径：及格 D / 良好 C / 优秀 B / 超优 A）",
         _tier_lines(gates, chosen)),
        ("代码规范与工具链（真实测量，不编造）",
         _style_lines(style, tools, pylint)),
        ("交付物清单", _artifact_lines(out_dir, notes_info, files)),
        ("结论与建议", _conclusion(runs, summary, gates, notes_info, chosen))]
    report.save(sections, os.path.join(out_dir, "report.txt"))
    io_utils.write_json(os.path.join(out_dir, "result.json"), result)
    return sections, result


def _exercise_lines(runs):
    lines = []
    for run_ in runs:
        lines.append("◆ %s %s" % (run_["number"], run_["title"]))
        lines.extend("   " + text for text in run_["lines"])
    return lines


def _assertion_lines(results, summary):
    lines = []
    for number in sorted(summary):
        bucket = summary[number]
        lines.append("%s: %s 断言 %d 条通过 %d 条（边界 %d/%d）"
                     % (number, "PASS" if bucket["pass"] else "FAIL",
                        bucket["total"], bucket["passed"],
                        bucket["boundary_passed"], bucket["boundary_total"]))
    for item in results:
        if not item["ok"]:
            lines.append("✗ 失败明细 %s[%s/%s] %s → %s"
                         % (item["number"], item["tier"], item["kind"],
                            item["label"], item["detail"]))
    return lines


def _tier_lines(gates, chosen):
    """分层达标输出：每档先给一行"工单要求+实测数字→判定"汇总，再列明细；
    最后单列保底自检（不计入工单档位），保留课堂跟做证据。"""
    lines = []
    marks = {True: "✔", False: "✘", None: "ℹ"}
    for tier in selfcheck.TIER_ORDER:
        info = gates["tiers"][tier]
        items = [g for g in gates["gates"] if g["tier"] == tier]
        scored = [g for g in items if g["ok"] is not None]
        mark = "（本轮请求层）" if tier == chosen else ""
        lines.append("【%s · %s层】达标=%s｜%d/%d 项通过%s"
                     % (tier, info["name"], info["verdict"],
                        sum(1 for g in scored if g["ok"]), len(scored), mark))
        lines.append("   %s" % info["summary"])
        for gate in items:
            lines.append("   [%s] %s" % (marks[gate["ok"]], gate["item"]))
    floor = gates["tiers"][selfcheck.FLOOR]
    floor_items = [g for g in gates["gates"] if g["tier"] == selfcheck.FLOOR]
    lines.append("【保底】%s" % floor["summary"])
    for gate in floor_items:
        lines.append("   [%s] %s" % (marks[gate["ok"]], gate["item"]))
    return lines


def _style_lines(style, tools, pylint):
    lines = ["内置 PEP 8 子集（标准库 tokenize/ast，非 pylint 评分）："
             "%.1f%% 通过（检查项 %d，违规 %d，行长上限 %d）"
             % (style["score"], style["total"], style["total"] -
                style["passed"], style["max_line_length"]),
             "   分类计数：命名 %d｜缺 docstring %d｜超长行 %d"
             % (style["naming_violations"], style["missing_docstrings"],
                style["long_lines"])]
    for name, info in sorted(tools.items()):
        lines.append("   工具探测 %-11s: %s%s" % (
            name, "可用 " + info["version"] if info["available"] else
            "不可用（%s）" % (info["reason"] or "未安装"), ""))
    if pylint.get("available"):
        lines.append("   pylint 实测评分：%.2f/10（阈值 8.5）"
                     % (pylint["score"] or 0.0))
    else:
        lines.append("   pylint 评分：不可用——本环境未安装，"
                     "故不输出任何百分比替代 pylint 结论")
    if style["top_violations"]:
        lines.append("   违规明细（前 %d 条）：" % len(style["top_violations"]))
        for item in style["top_violations"]:
            lines.append("     %s:%s %s %s" % (item[0], item[2], item[1],
                                                item[3]))
    return lines


def _artifact_lines(out_dir, notes_info, files):
    """交付物清单：全部落在本项目 output/ 与 docs/ 内（不外溢）。"""
    parent = os.path.dirname(os.path.abspath(out_dir))
    lines = ["output/report.txt（过程性证据主文档）",
             "output/result.json（结构化取数，供答辩/下游）",
             "output/%s/（题5 样例：正常/坏编码/空/大文件/目录探针）"
             % SAMPLES_DIR]
    for key in ("sample", "bad", "empty", "large", "dir", "missing"):
        path = files.get(key)
        if not path:
            continue
        suffix = "（按设计不存在：题5 缺失文件探针）" if key == "missing" \
            else ""
        lines.append("   - %s%s" % (os.path.relpath(path, parent), suffix))
    if notes_info.get("skipped"):
        lines.append("%s：本次 --no-notes 未生成，笔记相关的保底/超优 A 层"
                     "条目按未达标处理（不虚构）"
                     % NOTES_RELPATH.replace(os.sep, "/"))
    else:
        lines.append("%s（超优 A 层《迁移笔记》，实测 %d 条/要求 %d 条，"
                     "逐题易错点 %d/5，完整性达标=%s）"
                     % (NOTES_RELPATH.replace(os.sep, "/"),
                        notes_info["verified_entries"],
                        notes_info["required"],
                        notes_info.get("questions_covered", 0),
                        "是" if notes_info.get("complete") else "否"))
    return lines


def _conclusion(runs, summary, gates, notes_info, chosen):
    passed = [r["number"] for r in runs if summary.get(r["number"],
                                                       {}).get("pass")]
    failed = [r["number"] for r in runs if r["number"] not in passed]
    tier_ok = gates["tier_pass"].get(chosen, False)
    tier_name = gates["tiers"].get(chosen, {}).get("name", chosen)
    lines = ["五题通过 %d/5：%s%s" % (len(passed), "/".join(passed) or "无",
                                  "｜失败 %s" % "/".join(failed) if failed
                                  else ""),
             "工单档位 %s（%s）达标=%s；边界断言（空输入/极值/异常）每题 ≥3 条已%s"
             % (chosen, tier_name, "是" if tier_ok else "否",
                "全部通过" if all(s["boundary_enough"] for s in
                                  summary.values()) else "存在缺口"),
             "保底自检（不计入工单档位）达标=%s"
             % ("是" if gates["floor_pass"] else "否")]
    if notes_info.get("skipped"):
        lines.append("迁移笔记：本次 --no-notes 跳过，未生成/未更新 %s"
                     % notes_info["path"])
    else:
        lines.append("迁移笔记实测 %d 条（要求 ≥%d）+ 逐题易错点 %d/5 + "
                     "P1.2 布局映射章节齐全=%s，文件：%s" % (
                         notes_info["verified_entries"],
                         notes_info["required"],
                         notes_info.get("questions_covered", 0),
                         "是" if notes_info.get("sections_complete")
                         else "否", notes_info["path"]))
    if failed:
        lines.append("整改建议：优先修复失败题号，再复跑 `python run.py --tier A`")
    else:
        lines.append("复现与提交：pytest 全绿后按 `feat: P1.1 五题` 规范提交")
    return lines
