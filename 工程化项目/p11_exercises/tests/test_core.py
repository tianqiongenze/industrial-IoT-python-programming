# -*- coding: utf-8 -*-
"""core 层单测：每个核心函数正常 + 空输入 + 极值 + 异常四档。

对应 docs/04 用例清单 TC-C01~TC-C12；断言全部用裸 assert，
失败时 pytest 自动展示上下文（工单 B06 pytest 口径）。
"""
import pytest

from exercise_five import core


# ---------------- 题1 convert_temperature ----------------
def test_convert_returns_both_fahrenheit_and_kelvin():
    """工单硬要求：输入℃同时输出℉与K，缺一不可。"""
    assert core.convert_temperature(100) == (212.0, 373.15)
    fahr, kelvin = core.convert_temperature(0)
    assert (fahr, kelvin) == (32.0, 273.15)


@pytest.mark.parametrize("celsius", [36.6, 85.0, -10.5])
def test_convert_matches_formula(celsius):
    """公式校验：F=C*9/5+32、K=C+273.15（参数化覆盖多组）。"""
    fahr, kelvin = core.convert_temperature(celsius)
    assert abs(fahr - (celsius * 9 / 5 + 32)) < 1e-9
    assert abs(kelvin - (celsius + 273.15)) < 1e-9


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_convert_rejects_empty_input(blank):
    """空输入档：None/空串必须报错而不是返回 0。"""
    with pytest.raises(core.ExerciseError):
        core.convert_temperature(blank)


def test_convert_accepts_numeric_string_from_input():
    """input() 返回 str 的坑：数字字符串必须可转换。"""
    assert core.convert_temperature("100")[0] == 212.0


def test_convert_absolute_zero_boundary():
    """极值档：绝对零度是允许的下界，K 恰为 0。"""
    assert core.convert_temperature(-273.15)[1] == pytest.approx(0.0)


def test_convert_below_absolute_zero_rejected():
    """异常档：低于绝对零度属物理不可能。"""
    with pytest.raises(core.ExerciseError) as exc:
        core.convert_temperature(-300)
    assert "低于绝对零度" in str(exc.value)


def test_convert_wrong_unit_rejected():
    """异常档：单位口径由配置决定，非 c 直接拒绝。"""
    with pytest.raises(core.ExerciseError):
        core.convert_temperature(100, unit="f")


def test_temperature_level_uses_config_thresholds():
    """阈值分级：warn/danger 全部来自配置，代码零硬编码。"""
    assert core.temperature_level(20, 80, 95) == core.LEVEL_NORMAL
    assert core.temperature_level(85, 80, 95) == core.LEVEL_WARN
    assert core.temperature_level(120, 80, 95) == core.LEVEL_DANGER
    with pytest.raises(core.ExerciseError):
        core.temperature_level(None, 80, 95)


# ---------------- 题2 solve_quadratic ----------------
def test_quadratic_two_real_roots():
    """正常档：x²-3x+2 → (2.0, 1.0)。"""
    assert core.solve_quadratic(1, -3, 2) == (2.0, 1.0)


def test_quadratic_no_real_root_returns_none():
    """正常档：Δ<0 分支返回 None（工单"含无实根分支"）。"""
    assert core.solve_quadratic(1, 0, 1) is None


def test_quadratic_double_root():
    """正常档：Δ=0 重根。"""
    assert core.solve_quadratic(1, 2, 1) == (-1.0, -1.0)


@pytest.mark.parametrize("bad", [(None, 1, 1), (1, "", 1), (1, 1, "  ")])
def test_quadratic_rejects_empty_input(bad):
    """空输入档：任一系数为空都拒绝。"""
    with pytest.raises(core.ExerciseError):
        core.solve_quadratic(*bad)


def test_quadratic_extreme_coefficients_are_stable():
    """极值档：b=-1e6 时小根仍精确（稳定式，防灾难性抵消）。"""
    x1, x2 = core.solve_quadratic(1, -1000000, 1)
    assert abs(x1 + x2 - 1000000.0) < 1e-6
    assert abs(1.0 * x2 * x2 - 1000000.0 * x2 + 1.0) < 1e-6


def test_quadratic_a_zero_is_not_quadratic():
    """异常档：a=0 退化成一次方程，必须拒绝。"""
    with pytest.raises(core.ExerciseError) as exc:
        core.solve_quadratic(0, 1, 1)
    assert "a=0" in str(exc.value)


# ---------------- 题3 normalize_id / Registry ----------------
@pytest.mark.parametrize("value,expected", [(1, "01"), ("01", "01"),
                                            (2, "02"), ("DEV-01", "DEV-01")])
def test_normalize_id_zero_pads(value, expected):
    """键类型归一：PyYAML 把 01 读成整数 1，统一回 '01'。"""
    assert core.normalize_id(value, 2) == expected


def test_normalize_id_wide_and_narrow():
    """极值档：宽度可变，超宽不截断。"""
    assert core.normalize_id(7, 4) == "0007"
    assert core.normalize_id("12345", 2) == "12345"


@pytest.mark.parametrize("blank", [None, "", "  "])
def test_normalize_id_rejects_empty(blank):
    """空输入档：空 ID 不允许成为键。"""
    with pytest.raises(core.ExerciseError):
        core.normalize_id(blank)


def test_registry_crud_and_real_delete():
    """正常档：增改查删全链路，删除必须真的少一台。"""
    reg = core.Registry(2, core.STATUS_STOP)
    reg.add(1, "注塑机A", "运行")
    reg.add(2, "冷却泵B")
    reg.add(3, "空压机C")
    assert reg.count() == 3 and reg.ids() == ["01", "02", "03"]
    reg.update("03", status=core.STATUS_RUN)
    assert reg.get("03").status == core.STATUS_RUN
    assert reg.remove("02") is not None
    assert reg.count() == 2 and "02" not in reg.ids()


def test_registry_bulk_extreme():
    """极值档：500 台批量增删后计数自洽。"""
    reg = core.Registry(4, core.STATUS_STOP)
    for idx in range(500):
        reg.add(idx, "设备%d" % idx)
    assert reg.count() == 500
    reg.remove(0)
    reg.remove(499)
    assert reg.count() == 498


def test_registry_duplicate_add_rejected():
    """异常档：同 ID 二次新增必须报错，不静默覆盖。"""
    reg = core.Registry()
    reg.add("01", "A")
    with pytest.raises(core.ExerciseError):
        reg.add(1, "B")


def test_registry_update_missing_raises():
    """异常档：改不存在的设备直接报错（比返回 None 更早暴露）。"""
    with pytest.raises(core.ExerciseError):
        core.Registry().update("88", status="运行")


def test_registry_remove_missing_returns_none():
    """异常档：删不存在的键返回 None，调用方可判定未生效。"""
    assert core.Registry().remove("99") is None


def test_registry_update_rejects_unknown_field():
    """异常档：只允许改 name/status，主键与其它字段拒绝。"""
    reg = core.Registry()
    reg.add("01", "A")
    with pytest.raises(core.ExerciseError):
        reg.update("01", dev_id="05")
    with pytest.raises(core.ExerciseError):
        reg.update("01", name="   ")


def test_registry_top_uses_topk():
    """配置驱动：topk 只在这里消费，非死配置。"""
    reg = core.Registry()
    for idx in (1, 2, 3):
        reg.add(idx, "设备%d" % idx)
    assert [row["dev_id"] for row in reg.top(2)] == ["01", "02"]
    assert len(reg.top(0)) == 0


# ---------------- 题4 Device / PLC ----------------
def test_device_base_start_stop():
    """正常档：基类行为与状态流转。"""
    dev = core.Device("01", "空压机")
    assert dev.status == core.STATUS_STOP
    assert dev.start() == "空压机启动" and dev.status == core.STATUS_RUN
    assert dev.stop() == "空压机停止" and dev.status == core.STATUS_STOP


def test_plc_extends_device_and_overrides_start():
    """正常档：子类新增 scan_ms + scan()，并覆盖 start() 文案。"""
    plc = core.PLC("01", "S7-1200", 8)
    assert isinstance(plc, core.Device)
    assert plc.status == core.STATUS_STOP
    assert plc.start() == "S7-1200启动, 扫描8ms"
    assert plc.status == core.STATUS_RUN
    assert plc.scan(2) == ["第1轮扫描: S7-1200 status=运行 cycle=8ms",
                           "第2轮扫描: S7-1200 status=运行 cycle=8ms"]


@pytest.mark.parametrize("bad_id,bad_name,bad_scan",
                         [(None, "机", 10), ("01", "", 10), ("01", "机", None),
                          ("01", "机", "  ")])
def test_plc_rejects_empty_inputs(bad_id, bad_name, bad_scan):
    """空输入档：ID/名称/扫描周期任一为空都拒绝。"""
    with pytest.raises(core.ExerciseError):
        core.PLC(bad_id, bad_name, bad_scan)


def test_plc_accepts_max_scan_ms_extreme():
    """极值档：上限值本身合法。"""
    assert core.PLC("01", "机", 10000, scan_ms_max=10000).scan_ms == 10000


def test_plc_scan_rounds_extremes():
    """极值档：0 轮返回空列表，1000 轮返回 1000 条。"""
    plc = core.PLC("01", "机", 10)
    plc.start()
    assert plc.scan(0) == []
    assert len(plc.scan(1000)) == 1000


@pytest.mark.parametrize("scan_ms", [0, -5, 10001, 3.5, "abc", True])
def test_plc_rejects_bad_scan_ms(scan_ms):
    """异常档：非正整数/超上限/类型错误全部拒绝。"""
    with pytest.raises(core.ExerciseError):
        core.PLC("01", "机", scan_ms, scan_ms_max=10000)


def test_plc_scan_requires_start_first():
    """异常档：未启动不能扫描（状态机约束）。"""
    with pytest.raises(core.ExerciseError):
        core.PLC("01", "机", 10).scan(1)


@pytest.mark.parametrize("rounds", [-1, 1001, "x"])
def test_plc_scan_rejects_bad_rounds(rounds):
    """异常档：轮次越界或非整数。"""
    plc = core.PLC("01", "机", 10)
    plc.start()
    with pytest.raises(core.ExerciseError):
        plc.scan(rounds)


# ---------------- 题5 safe_read ----------------
def test_safe_read_returns_content(files):
    """正常档：存在的 utf-8 文件读回原文。"""
    assert core.safe_read(files["sample"]) == "设备清单表头：id,name,status"


def test_safe_read_missing_file(files):
    """正常档（约定分支）：缺失返回 FILE_NOT_FOUND 而非抛异常。"""
    assert core.safe_read(files["missing"]) == core.FILE_NOT_FOUND


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_safe_read_empty_path(blank):
    """空输入档：空路径返回 EMPTY_PATH，不去猜目录。"""
    assert core.safe_read(blank) == core.EMPTY_PATH


def test_safe_read_empty_file_extreme(files):
    """极值档：0 字节文件是合法内容，返回空串。"""
    assert core.safe_read(files["empty"]) == ""


def test_safe_read_large_file_extreme(files):
    """极值档：200 行文件行数正确。"""
    assert len(core.safe_read(files["large"]).splitlines()) == 200


def test_safe_read_bad_encoding(files):
    """异常档：非 utf-8 字节流返回 BAD_ENCODING。"""
    assert core.safe_read(files["bad"]) == core.BAD_ENCODING


def test_safe_read_directory(files):
    """异常档：传目录返回 IS_DIRECTORY（不是崩溃）。"""
    assert core.safe_read(files["dir"]) == core.IS_DIRECTORY


def test_safe_read_deep_missing_path(files):
    """异常档：深层不存在路径同样兜住。"""
    assert core.safe_read("%s/a/b.txt" % files["dir"]) == core.FILE_NOT_FOUND
