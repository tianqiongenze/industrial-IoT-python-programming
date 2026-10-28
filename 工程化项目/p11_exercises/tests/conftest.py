# -*- coding: utf-8 -*-
"""共享 fixture：真实配置 + 题5 样例文件（落在 pytest 临时目录）。

工程约定：测试绝不往仓库 output/ 写东西（tmp_path 沙箱），
两次运行互不影响，符合"生成物只留在各自 output/"的纪律。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from exercise_five import config, pipeline  # noqa: E402

CONFIG_PATH = os.path.join(ROOT, "config", "rules.yaml")


@pytest.fixture(scope="session")
def project_root():
    """项目根目录（stylecheck/notes 定位用）。"""
    return ROOT


@pytest.fixture(scope="session")
def cfg():
    """真实生产配置（config/rules.yaml），全量测试共用。"""
    return config.load_config(CONFIG_PATH)


@pytest.fixture()
def files(tmp_path, cfg):
    """在临时目录里造题5 需要的样例文件，返回路径字典。"""
    return pipeline.prepare_samples(cfg, str(tmp_path))
