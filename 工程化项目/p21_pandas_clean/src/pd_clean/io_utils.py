# -*- coding: utf-8 -*-
"""输入输出工具：读 CSV/JSON、原子写文本、保证目录存在。

工程要点：
  1. 原子写（先写临时文件再 os.replace）——防止中途崩溃留下半个文件；
  2. 所有路径参数为绝对/相对均可，内部统一 os.path.join；
  3. 失败时抛带文件名的异常，便于排错（对应 GB/T 15532 异常路径测试）。
"""
import csv
import hashlib
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


def write_json(path, obj, default=None):
    return write_text(path, json.dumps(obj, ensure_ascii=False, indent=2,
                                       sort_keys=True, default=default))


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_text(path):
    """读 UTF-8 文本文件（文档使用示例定位等只读场景）。"""
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_csv_rows(path):
    """按行读 CSV，返回 list[dict]；首行视为表头。

    管道第 0 步用它核对"物理行数/表头列名"，与 pandas 解析出的逻辑行数对账——
    两者不一致即说明存在换行/引号/编码类脏格式，摸底阶段必须先看见。
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def sha256_short(path, length=12):
    """输入文件指纹（确定性，替代报告里的"生成时间戳"以保证逐字节可复现）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:length]


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

