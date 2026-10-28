# -*- coding: utf-8 -*-
"""产线数据仓库 ORM —— 工程化实现包（SQLAlchemy 2.x + SQLite）。

分层：config（配置）/ models（ORM 声明式四表）/ core（引擎·入库·查询·基准）/
io_utils（IO）/ report（报告）/ pipeline（编排）。
"""
__version__ = "2.0.0"
__all__ = ["config", "models", "core", "io_utils", "report", "pipeline"]
