# -*- coding: utf-8 -*-
"""报告渲染：把结果渲染为等宽文本报告并落盘（utf-8）。

报告是工单与期末答辩的**过程性证据**（对应 GB/T 8567 文档编制），
必须包含：输入口径、处理过程指标、结论与建议四段。
"""
import datetime

from . import io_utils


def render(sections):
    """sections: [(标题, [行, ...]), ...] -> 文本"""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = ["=" * 64, "生成时间: %s" % ts, "=" * 64]
    for title, lines in sections:
        out.append("")
        out.append("[%s]" % title)
        out.append("-" * 64)
        out.extend(str(x) for x in lines)
    out.append("")
    return "\n".join(out)


def save(sections, path):
    text = render(sections)
    io_utils.write_text(path, text)
    return text


def console(sections):
    print(render(sections))
