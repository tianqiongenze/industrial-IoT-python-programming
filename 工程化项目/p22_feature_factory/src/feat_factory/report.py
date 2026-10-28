# -*- coding: utf-8 -*-
"""报告渲染：把结果渲染为等宽文本报告并落盘（utf-8）。

报告是工单与期末答辩的**过程性证据**（对应 GB/T 8567 文档编制），
必须包含：输入口径、处理过程指标、结论与建议四段。

可复现性说明（NF-1）：报告头不放"生成时间"这类墙钟字段，改放**输入文件指纹
（sha256）**——同一输入两次运行逐字节一致；确需时间戳时用 `--stamp` 显式开启。
"""
import datetime

from . import io_utils

HEADER = "P2.2 NumPy 故障特征提取系统 · 特征与性能报告"


def render(sections, title=HEADER, stamp=None):
    """sections: [(标题, [行, ...]), ...] -> 文本；stamp=None 时不写墙钟。"""
    out = ["=" * 68, title, "=" * 68]
    if stamp:
        out.append("生成时间: %s" % stamp)
    for name, lines in sections:
        out.append("")
        out.append("[%s]" % name)
        out.append("-" * 68)
        out.extend(str(x) for x in lines)
    out.append("")
    return "\n".join(out)


def save(sections, path, title=HEADER, stamp=None):
    text = render(sections, title, stamp)
    io_utils.write_text(path, text)
    return text


def console(sections, title=HEADER, stamp=None):
    print(render(sections, title, stamp))


def now_stamp():
    """供 --stamp 使用的墙钟串（默认不调用，以保持输出可复现）。"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
