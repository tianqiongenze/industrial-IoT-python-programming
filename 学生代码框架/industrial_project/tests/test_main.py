"""单元测试: pytest自动发现test_开头函数"""
from src.main import main


def test_main_runs():
    assert main() is None
