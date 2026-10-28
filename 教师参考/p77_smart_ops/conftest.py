# -*- coding: utf-8 -*-
"""pytest 引导：把项目根加进 sys.path，并把五库路径指到一次性临时目录。

为什么需要：教学版 config.py 在 import 时就把 DATA 定死了；
测试若复用 data/，会污染随仓库分发的演示数据（且并行跑互相踩）。
conftest 先于测试模块被导入，因此这里设的环境变量对全部被测模块生效。
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_TMP_DATA = tempfile.mkdtemp(prefix="p77_test_")
os.environ.setdefault("P77_DATA_DIR", _TMP_DATA)
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:1/0")   # 端口1必不可达→走回退链
