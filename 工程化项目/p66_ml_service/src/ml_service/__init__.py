# -*- coding: utf-8 -*-
"""故障诊断模型与边缘部署 —— 工程化实现包（sklearn 五步流 + http.server 服务化）。

分层：config（配置）/ data（P2.2 数据链与特征契约）/ core（训练·评估·门禁）/
service（推理服务与压测）/ bridge（P5 库联动回写）/ onnx_export（A层边缘对比）/
io_utils（IO）/ report（报告）/ pipeline（编排）。
"""
__version__ = "2.0.0"
__all__ = ["config", "data", "core", "service", "bridge", "onnx_export",
           "io_utils", "report", "pipeline"]
