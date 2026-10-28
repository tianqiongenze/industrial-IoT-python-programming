# -*- coding: utf-8 -*-
"""输入输出工具：读 CSV/JSON、原子写文本、保证目录存在。

工程要点：
  1. 原子写（先写临时文件再 os.replace）——防止中途崩溃留下半个文件；
  2. 所有路径参数为绝对/相对均可，内部统一 os.makedirs 保证目录存在；
  3. 只保留本项目真实用到的函数（无死代码）。
"""
import csv
import json
import os
import tempfile


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def write_text(path, text, encoding="utf-8"):
    """原子写入：先写临时文件再替换，避免半成品文件。"""
    ensure_dir(os.path.dirname(os.path.abspath(path)))
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)),
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def write_json(path, obj):
    return write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))


def write_csv_rows(path, rows, fields=None):
    """附表落 CSV（日报第四段的机读版本，供下游/答辩取数）。"""
    if not rows:
        return write_text(path, "")
    fields = fields or list(rows[0].keys())
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return write_text(path, buf.getvalue())
