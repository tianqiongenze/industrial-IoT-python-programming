# -*- coding: utf-8 -*-
"""Python 五题闯关 —— 工程化实现包（工单 P1.1）。

分层：config（配置）/ core（纯逻辑）/ exercises（一题一函数）/
selfcheck（内置断言+工单分层达标）/ stylecheck（规范度量+工具探测）/
testmap（每题 pytest 用例实测）/ notes（迁移笔记）/ io_utils（IO）/
report（报告）/ pipeline（编排）/ cli（入口）。
"""
__version__ = "2.2.0"
__all__ = ["cli", "config", "core", "exercises", "io_utils", "notes",
           "pipeline", "report", "selfcheck", "stylecheck", "testmap"]
