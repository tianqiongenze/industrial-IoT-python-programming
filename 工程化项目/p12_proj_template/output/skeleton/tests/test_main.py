"""单元测试：pytest 自动发现 test_ 开头函数（正常/边界/异常三档）。"""
from src.main import main
from src.utils import celsius_to_fahrenheit


def test_main_runs():
    assert main() == 0


def test_convert():
    assert celsius_to_fahrenheit(100) == 212


def test_convert_boundary_zero():
    assert celsius_to_fahrenheit(0) == 32
