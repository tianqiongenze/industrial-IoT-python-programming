# -*- coding: utf-8 -*-
"""输入输出工具：读 CSV/JSON、原子写文本、保证目录存在。

工程要点：
  1. 原子写（先写临时文件再 os.replace）——防止中途崩溃留下半个文件；
  2. 所有路径参数为绝对/相对均可，内部统一 os.path.join；
  3. 失败时抛带文件名的异常，便于排错（对应 GB/T 15532 异常路径测试）。
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


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_csv_rows(path):
    """按行读 CSV，返回 list[dict]；首行视为表头。"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def write_csv_rows(path, rows, fields=None):
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


def fmt_table(rows, headers):
    """等宽文本表（报告用）——不依赖第三方库。"""
    cols = [list(headers)] + [[str(c) for c in r] for r in rows]
    widths = [max(len(r[i]) for r in cols) for i in range(len(headers))]
    out = ["  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)),
           "  ".join("-" * w for w in widths)]
    for r in cols[1:]:
        out.append("  ".join(c.ljust(widths[i]) for i, c in enumerate(r)))
    return "\n".join(out)
