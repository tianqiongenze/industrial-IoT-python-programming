# -*- coding: utf-8 -*-
"""按配置生成标准工程骨架 → 读盘核对 → 算出 D/C/B/A 分层达标证据 → 落盘报告。

分层口径（与工单 P1.2 表格逐条对应，全部由**生成物真实内容**推导，不写死）：
  D 学徒  跟做跑通：四目录齐备 + 模板文件全部落盘 + [project.scripts] 入口真能解析
  C 操作员 venv 可用 + 仓库就绪：scripts/setup_venv.sh 的 venv/依赖/git init 三连 + .gitignore 屏蔽 venv/
  B 组长  依赖可还原 + dev 分支规范合并：双清单钉版本下限（-r 引用）+ scripts/git_dev_branch.sh
  A 师傅  规范闸门：.pre-commit-config.yaml 逐工具声明 local hook；工具在本机能否导入由
          env_probe 真实探测，未安装就如实写"本次未运行"，绝不谎报 black/flake8 跑过
另有一节「工单验收四档对照」：按工单《P1.2》验收标准的 及格/良好/优秀/超优 四行原文重新取证
（与课堂四档不同轴，尤其 良好(C)『检查工具配置生效；pytest通过』课堂闸门不覆盖）。
本模块不执行任何 git / venv / pip / 检查工具命令；唯一的真跑是 core.skeleton_smoke()
在本进程内加载生成骨架、调用它的入口与自带的 test_ 函数。
"""
import os

from . import core, env_probe, io_utils, report


def _b(installed):
    return "是" if installed else "否"


def _wo_lines(facts, rep, smoke, conda, wo, wo_ext):
    """工单《P1.2》验收标准四行：原文逐字照抄 + 本机实测数字 + 点名未实测的子项。"""
    structure = core.structure_ok(facts, rep)
    hooks = ", ".join(facts["hook_declared"]) or "无"
    ev = {
        "D": "结构完整=%s（四目录 %d/%d、模板缺失 %d、空目录 %d、.pyc %d）｜README.md 已落盘 %d 字节"
             "且首行为一级标题=%s｜仓库初始化三连（git init / git add . / git commit -m）=%s｜"
             "venv 激活命令写在 setup_venv.sh=%s｜本流水线解释器位于 conda 环境目录=%s"
             % (_b(structure), facts["dirs_present"], facts["dirs_total"], len(rep["missing"]),
                len(rep["empty_dirs"]), len(rep["junk"]), facts["readme_bytes"],
                _b(facts["readme_titled"]), _b(facts["git_repo_seq"]),
                _b(facts["venv_activate"]), _b(conda["in_conda_envs"])),
        "C": "检查工具配置：%d 个钩子全部带 entry（%d/%d，%s）｜配置要求的工具缺口 %d 个｜"
             "pytest 配置 testpaths 已声明=%s｜生成骨架真实加载：入口 main() 返回 %s、"
             "自带 test_ 函数 %d 个通过 %d 个失败 %d 个｜--fail-under 评分 entry 已声明=%s"
             % (facts["hook_with_entry"], facts["hook_with_entry"],
                len(facts["hook_declared"]), hooks, len(facts["hook_missing"]),
                _b(facts["pytest_cfg_declared"]), smoke["entry_returned"],
                smoke["tests_found"], len(smoke["tests_passed"]),
                len(smoke["tests_failed"]), _b(facts["fail_under_declared"])),
        "B": "运行依赖 %d/%d 条钉下限｜开发依赖 %d/%d 条钉下限｜-r 引用 requirements.txt=%s｜"
             "与运行依赖重名的开发项 %d 个（%s）｜git branch dev=%s、git checkout dev=%s、"
             "--no-ff 合并=%s"
             % (facts["runtime_dep_pinned"], facts["runtime_dep_total"],
                facts["dev_dep_pinned"], facts["dev_dep_total"], _b(facts["dev_ref_runtime"]),
                len(facts["dep_dupes"]), ", ".join(facts["dep_dupes"]) or "无",
                _b(facts["dev_branch"]), _b(facts["dev_checkout"]), _b(facts["no_ff_merge"])),
        "A": "pre-commit 钩子文件已产出=%s（声明 %d 个：%s）｜.github/workflows 下 CI 文件 %d 个%s｜"
             "工单优秀(B) 档前置=%s"
             % (_b(facts["pre_commit_declared"]), len(facts["hook_declared"]), hooks,
                len(facts["ci_workflows"]),
                "" if not facts["ci_workflows"] else "：" + ", ".join(facts["ci_workflows"]),
                "成立" if wo["B"] else "不成立"),
    }
    lines = ["档位口径说明：本节判的是工单《P1.2》验收标准四行原文，与上面「分层达标」的课堂四档"
             "（D 跟做 / C 基础 / B 标准 / A 进阶拓展）不同轴；两节各判各的、互不覆写。"
             "凡一档还有本机取不了证的子项（要真开 shell / 真联网 / 真触发 git 钩子），"
             "该行只写「本节取证项 通过」，绝不写「达标」。"]
    for k, tag in (("D", "及格"), ("C", "良好"), ("B", "优秀"), ("A", "超优")):
        head = "工单%s(%s)「%s」: " % (tag, k, core.WO_ROW[k])
        if not wo[k]:
            verdict = "→ 未达标"
        elif wo_ext[k]:
            verdict = "→ 本节取证项 通过"
        else:
            verdict = "→ 达标"
        lines.append(head + ev[k] + " " + verdict)
        if wo_ext[k]:
            lines.append("    未取证项（须课堂/CI 侧补跑）：%s" % "；".join(wo_ext[k]))
    return lines


def run(cfg, out_dir):
    raw = cfg.raw
    name = str(raw.get("project_name", "pump-ops"))
    deps = [str(x) for x in (raw.get("deps") or [])]
    dev_deps = [str(x) for x in (raw.get("dev_deps") or core.DEFAULT_DEV_DEPS)]
    lint_tools = [str(x) for x in (raw.get("lint_tools") or core.DEFAULT_LINT_TOOLS)]
    pyver = str(raw.get("python_version", ">=3.10"))
    with_pc = bool(raw.get("emit_pre_commit", True))
    overwrite = bool(raw.get("overwrite_existing", True))

    root = os.path.join(out_dir, "skeleton")
    files = core.file_templates(name, deps, dev_deps=dev_deps, lint_tools=lint_tools,
                                python_version=pyver, pre_commit=with_pc)
    core.ensure(root, files, overwrite=overwrite)
    rep = core.verify(root, files)
    ok = not rep["missing"] and not rep["empty_dirs"] and not rep["junk"]

    facts = core.layer_facts(root, files, lint_tools)
    tiers = core.layer_gates(facts, rep, lint_tools)
    inv = core.inventory(root, files)
    bytes_total = sum(v for v in inv.values() if v is not None)

    probe_names = sorted(set(core.LINT_ENTRY) | set(env_probe.TOOLS) | set(lint_tools))
    probes = env_probe.detect(probe_names)
    by_name = {p["name"]: p for p in probes}
    lint_usable = [n for n in lint_tools if by_name.get(n, {"installed": False})["installed"]]
    hook_lines = env_probe.report_lines(probes, facts["hook_declared"])

    smoke = core.skeleton_smoke(root)
    conda = core.conda_env()
    wo, wo_ext = core.workorder_gates(facts, rep, smoke, conda)
    wo_lines = _wo_lines(facts, rep, smoke, conda, wo, wo_ext)

    tier_lines = [
        "D层 跟做跑通: 模板 %d 个文件已落盘（共 %d 字节）｜[project.scripts] 入口解析 %d/%d"
        "｜四目录齐备 %d/%d｜自检 missing=%d empty_dirs=%d junk=%d → %s"
        % (len(files), bytes_total, facts["entry_resolved"], facts["entry_total"],
           facts["dirs_present"], facts["dirs_total"], len(rep["missing"]),
           len(rep["empty_dirs"]), len(rep["junk"]), "通过" if tiers["D"] else "未通过"),
        "C层 venv+仓库: setup_venv.sh 含 python -m venv venv=%s、pip install -r requirements.txt=%s、"
        "git init=%s｜.gitignore 屏蔽 venv/=%s → %s"
        % (_b(facts["venv_cmd"]), _b(facts["venv_pip_restore"]), _b(facts["git_init"]),
           _b(facts["gitignore_venv"]), "达标" if tiers["C"] else "未达标"),
        "B层 依赖可还原+dev分支: 运行依赖 %d/%d 条钉版本下限｜开发依赖 %d/%d 条钉下限，"
        "-r 引用 requirements.txt=%s｜git_dev_branch.sh 含 git branch dev=%s、"
        "git checkout dev=%s、--no-ff 合并=%s → %s"
        % (facts["runtime_dep_pinned"], facts["runtime_dep_total"],
           facts["dev_dep_pinned"], facts["dev_dep_total"], _b(facts["dev_ref_runtime"]),
           _b(facts["dev_branch"]), _b(facts["dev_checkout"]), _b(facts["no_ff_merge"]),
           "达标" if tiers["B"] else "未达标"),
        "A层 pre-commit 闸门: .pre-commit-config.yaml 声明钩子 %d 个（%s）｜配置要求工具 %d 个，"
        "缺钩子 %d 个｜本机可导入闸门工具 %d/%d → 闸门文件 %s；未安装的工具本次未运行（不谎报）"
        % (len(facts["hook_declared"]), ", ".join(facts["hook_declared"]) or "无",
           len(lint_tools), len(facts["hook_missing"]), len(lint_usable), len(lint_tools),
           "达标" if tiers["A"] else "未达标"),
    ]

    result = {"name": name, "n_files": len(files), "bytes_total": bytes_total,
              "files": inv, "verify": rep, "passed": ok,
              "layers": facts, "tiers": tiers, "tier_lines": tier_lines,
              "workorder_rows": dict(core.WO_ROW), "workorder_tiers": wo,
              "workorder_lines": wo_lines, "workorder_unmeasured": wo_ext,
              "workorder_evidence": {"skeleton_smoke": smoke, "conda_env": conda,
                                     "readme_bytes": facts["readme_bytes"],
                                     "generated_tests": facts["generated_tests"],
                                     "hook_with_entry": facts["hook_with_entry"],
                                     "ci_workflows": facts["ci_workflows"],
                                     "dep_dupes": facts["dep_dupes"]},
              "lint_tools": lint_tools, "emit_pre_commit": with_pc,
              "overwrite_existing": overwrite, "python_version": pyver,
              "deps": deps, "dev_deps": dev_deps,
              "probes": {p["name"]: {"installed": p["installed"], "version": p["version"]}
                         for p in probes},
              "probe_summary": env_probe.summary(probes),
              "config_echo": {"project_name": name, "deps": deps, "dev_deps": dev_deps,
                              "lint_tools": lint_tools, "python_version": pyver,
                              "emit_pre_commit": with_pc,
                              "overwrite_existing": overwrite}}
    os.makedirs(out_dir, exist_ok=True)
    io_utils.write_json(os.path.join(out_dir, "result.json"), result)
    sections = [
        ("输入口径", ["项目 %s｜Python %s｜运行依赖 %d 条｜开发依赖 %d 条｜闸门工具 %s"
                    % (name, pyver, len(deps), len(dev_deps), ", ".join(lint_tools) or "无"),
                      "模板 %d 个文件（表驱动）；生成到 %s；生成物按模板同步=%s"
                      "（同步=内容不一致才重写，一致则保留，故重复运行逐字节一致）"
                      % (len(files), os.path.relpath(root, out_dir), _b(overwrite))]),
        ("生成清单（文件盘点）",
         ["%-28s %6s 字节" % (rel, "-" if size is None else size)
          for rel, size in sorted(inv.items())]
         + ["小计 %d 个文件 / %d 字节｜缺失 %d 个"
            % (len(inv), bytes_total, sum(1 for v in inv.values() if v is None))]),
        ("规范闸门环境探测（A 层：只探测，不执行任何检查工具）", hook_lines),
        ("工单验收四档对照（及格/良好/优秀/超优）", wo_lines),
        ("分层达标", tier_lines),
        ("自检", ["missing=%d empty_dirs=%d junk=%d unexpected=%d"
                  % (len(rep["missing"]), len(rep["empty_dirs"]), len(rep["junk"]),
                     len(rep["unexpected"]))
                  + ("｜模板外文件：%s" % ", ".join(rep["unexpected"])
                     if rep["unexpected"] else "")]),
        ("结论与建议",
         ["四层达标 %s：%s" % ("/".join(k for k in "DCBA" if tiers[k]) or "无",
                              "、".join("%s=%s" % (k, _b(tiers[k])) for k in "DCBA")),
          "工单四档取证项 %d/4 通过：%s｜未取证子项合计 %d 条（逐条点名见对照节）"
          % (sum(1 for k in "DCBA" if wo[k]),
             "、".join("%s=%s" % (k, "取证项通过" if wo[k] else "未达标") for k in "DCBA"),
             sum(len(v) for v in wo_ext.values())),
          "新人第一天即得到可运行、可还原依赖、带钩子文件与分支脚本的工程骨架；"
          "课堂按 docs/05 逐条执行 scripts/ 内命令并截图进工单。",
          "若要把 A 层从『闸门文件已就位』升级成『提交真被拦截』：pip install -r requirements-dev.txt"
          " && pre-commit install（本机缺 %s）"
          % (", ".join(env_probe.missing_names(probes)) or "无")]),
    ]
    report.save(sections, os.path.join(out_dir, "report.txt"))
    return sections
