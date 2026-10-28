# -*- coding: utf-8 -*-
"""报告渲染：把结果渲染为等宽文本报告并落盘（utf-8）。

报告是工单与期末答辩的**过程性证据**（对应 GB/T 8567 文档编制），
固定包含：输入口径 / 逐题结果 / 内置断言 / 分层达标 / 代码规范与
工具链 / 交付物清单 / 结论建议。

纪律：正文不含时间戳——两次 `python run.py` 必须字节级一致（NF-1
可复现），需要时间请在 shell 侧 `date` 记录，不进基线文件。
"""
from . import io_utils

LINE = "=" * 68
SUB = "-" * 68


def render(sections, title="Python 五题闯关（工单 P1.1）过程报告"):
    """sections: [(标题, [行, ...]), ...] -> 报告文本。"""
    out = [LINE, title,
           "复现命令: python run.py（结果确定性：不含时间戳/随机源）", LINE]
    for name, lines in sections:
        out.append("")
        out.append("[%s]" % name)
        out.append(SUB)
        out.extend(str(x) for x in lines)
    out.append("")
    return "\n".join(out)


def save(sections, path, title=None):
    """渲染 + 原子写入，返回文本。"""
    text = render(sections, title) if title else render(sections)
    io_utils.write_text(path, text)
    return text


def console(sections, title=None):
    """控制台打印同一份文本（保证"看到的=落盘的"）。"""
    text = render(sections, title) if title else render(sections)
    print(text)
    return text
