# -*- coding: utf-8 -*-
"""五题实现：单位换算 / 一元二次 / 设备CRUD / PLC子类 / 安全读取。"""


def c_to_f(celsius):
    """摄氏度 → 华氏度。"""
    return celsius * 9.0 / 5.0 + 32.0


def kpa_to_mpa(kpa):
    return kpa / 1000.0


def quad(a, b, c):
    """一元二次方程：返回根列表；判别式<0 返回复根描述。"""
    d = b * b - 4 * a * c
    if d < 0:
        return ["complex"]
    if d == 0:
        return [-b / (2 * a)]
    import math
    r = math.sqrt(d)
    return [(-b + r) / (2 * a), (-b - r) / (2 * a)]


class Device:
    def __init__(self, code, name):
        self.code, self.name = code, name


class PLC(Device):
    """PLC 子类：扩展扫描周期（ms）。"""
    def __init__(self, code, name, scan_ms=100):
        super().__init__(code, name)
        self.scan_ms = scan_ms


class Registry:
    """设备增删改查（字典为存储，O(1) 查找）。"""
    def __init__(self):
        self._d = {}

    def add(self, dev):
        self._d[dev.code] = dev
        return dev

    def remove(self, code):
        return self._d.pop(code, None)

    def get(self, code):
        return self._d.get(code)

    def count(self):
        return len(self._d)


def safe_read(path):
    """异常保护读取：文件不存在返回标记而非崩溃。"""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "FILE_NOT_FOUND"
