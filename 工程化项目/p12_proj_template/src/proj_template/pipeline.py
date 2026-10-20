# -*- coding: utf-8 -*-
"""按配置生成标准工程骨架，并强制自检。"""
import os

from . import core, io_utils, report


def run(cfg, out_dir):
    name = str(cfg.raw.get("project_name", "pump-ops"))
    deps = cfg.raw.get("deps") or []
    root = os.path.join(out_dir, "skeleton")
    os.makedirs(root, exist_ok=True)
    files = core.file_templates(name, deps)
    made, kept = core.ensure(root, files)
    rep = core.verify(root, files)
    ok = not rep["missing"] and not rep["empty_dirs"] and not rep["junk"]
    result = {"name": name, "n_files": len(files), "made": made,
              "kept": kept, "verify": rep, "passed": ok}
    sections = [("输入口径", ["项目 %s｜依赖 %s｜模板 %d 个文件"
                % (name, "/".join(deps) or "无", len(files))]),
                ("生成结果", ["新建 %d 个：%s" % (len(made), ", ".join(made)),
                          "已存在跳过 %d 个" % len(kept)]),
                ("自检", ["missing=%d empty_dirs=%d junk=%d"
                 % (len(rep["missing"]), len(rep["empty_dirs"]), len(rep["junk"]))]),
                ("结论与建议", ["骨架自检 %s；新人第一天就在规范结构里写代码"
                 % ("通过" if ok else "失败——请检查模板表")])]
    os.makedirs(out_dir, exist_ok=True)
    report.save(sections, os.path.join(out_dir, "report.txt"))
    io_utils.write_json(os.path.join(out_dir, "result.json"), result)
    return sections
