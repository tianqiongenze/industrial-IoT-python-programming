# -*- coding: utf-8 -*-
"""P1.1 C→Python迁移五题 —— 框架(每题独立函数+测试断言)
运行: python W01_exercises.py            # 全部测试
     python W01_exercises.py 3           # 只跑第3题
"""
import sys


def ex1_temp_convert(c):
    """题1(⭐): 摄氏→(华氏, 开尔文)  F=C*9/5+32  K=C+273.15"""
    # === 你的代码 ===
    return 0.0, 0.0


def ex2_quadratic(a, b, c):
    """题2(⭐⭐): 一元二次方程, 返回根的元组; 无实根返回None"""
    # === 你的代码(含判别式分支) ===
    return None


def ex3_device_manager():
    """题3(⭐⭐): 设备增删改查(字典), 完成四个操作并返回最终字典"""
    devices = {}                     # id -> {"name":..., "status":...}
    # 1) 增加 DEV-01 空压机 运行
    # 2) 增加 DEV-02 冷却泵 停止
    # 3) 修改 DEV-02 状态为运行
    # 4) 删除 DEV-01
    # === 你的代码 ===
    return devices


class Device:                        # 题4用
    def __init__(self, dev_id, name):
        self.dev_id, self.name = dev_id, name
        self.status = "停止"


def ex4_plc_class():
    """题4(⭐⭐⭐): Device基类 + PLC子类(新增scan_ms, 覆盖start) → 返回PLC实例"""
    class PLC(Device):
        # === 你的代码 ===
        pass

    return PLC("DEV-01", "S7-1200", 8)


def ex5_safe_reader(path):
    """题5(⭐⭐): 读文件返回内容; 不存在返回"FILE_NOT_FOUND"; 编码错返回"BAD_ENCODING"
    必须用try/except, 禁止os.path.exists预判"""
    # === 你的代码 ===
    return ""


if __name__ == "__main__":
    answered = (ex1_temp_convert(100) != (0.0, 0.0)
                or ex2_quadratic(1, -3, 2) is not None
                or ex3_device_manager() != {}
                or ex5_safe_reader("not_exist.txt") != "")
    if not answered:
        print("五题闯关未开始——每题在'你的代码'处补全后重跑；先做题1(⭐)")
        sys.exit(0)
    assert abs(ex1_temp_convert(100)[0] - 212) < 1e-6
    assert ex2_quadratic(1, -3, 2) == (2.0, 1.0)
    assert ex2_quadratic(1, 0, 1) is None
    assert ex3_device_manager() == {"DEV-02": {"name": "冷却泵", "status": "运行"}}
    plc = ex4_plc_class()
    assert plc.scan_ms == 8
    assert ex5_safe_reader("not_exist.txt") == "FILE_NOT_FOUND"
    print("全部测试通过 ✓  (按需扩充边界断言冲击超优)")
