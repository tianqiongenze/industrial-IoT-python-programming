# -*- coding: utf-8 -*-
"""五题纯逻辑层：零 IO、零配置读取，参数由上层（exercises/pipeline）注入。

对应工单 P1.1 的五道渐进式练习题（一题一组可单测函数）：
  题1 convert_temperature()   ℃ → (℉, K)
  题2 solve_quadratic()       判别式三分支（两实根/重根/无实根）
  题3 Registry                设备清单增删改查（字典实现）
  题4 Device / PLC            基类 + 子类新增 scan_ms 并覆盖 start()
  题5 safe_read()             异常保护文件读取
"""
import math

ABSOLUTE_ZERO_C_DEFAULT = -273.15
FILE_NOT_FOUND = "FILE_NOT_FOUND"
BAD_ENCODING = "BAD_ENCODING"
EMPTY_PATH = "EMPTY_PATH"
IS_DIRECTORY = "IS_DIRECTORY"
READ_DENIED = "READ_DENIED"
LEVEL_NORMAL = "正常"
LEVEL_WARN = "预警"
LEVEL_DANGER = "危险"
STATUS_STOP = "停止"
STATUS_RUN = "运行"


class ExerciseError(ValueError):
    """业务异常：携带题号与出错参数上下文（对应 B04"异常携带业务信息"）。"""

    def __init__(self, exercise, message, **context):
        self.exercise = exercise
        self.context = dict(context)
        detail = "%s: %s" % (exercise, message)
        if context:
            detail += " | 参数=%s" % (self.context,)
        super().__init__(detail)


def to_number(value, exercise, field_name):
    """把 input() 返回的字符串安全转 float：空输入/非数字显式报错。"""
    if value is None:
        raise ExerciseError(exercise, "空输入", field=field_name, value=None)
    if isinstance(value, bool):
        raise ExerciseError(exercise, "不接受布尔值", field=field_name)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ExerciseError(exercise, "空输入(空字符串)", field=field_name)
        try:
            return float(text)
        except ValueError:
            raise ExerciseError(exercise, "非数字输入", field=field_name,
                                value=value) from None
    if isinstance(value, (int, float)):
        return float(value)
    raise ExerciseError(exercise, "不支持的参数类型", field=field_name,
                        type=type(value).__name__)


def convert_temperature(celsius, unit="c",
                        absolute_zero_c=ABSOLUTE_ZERO_C_DEFAULT):
    """题1：℃ → (℉, K)；F=C*9/5+32，K=C+273.15，两个结果都返回。

    参数：unit 仅支持 "c"（摄氏度）；absolute_zero_c 为物理下限。
    返回：二元组 (华氏度, 开尔文)。
    异常：空输入/非数字/低于绝对零度 → ExerciseError。
    """
    if str(unit).lower() != "c":
        raise ExerciseError("题1", "仅支持摄氏度输入", unit=unit)
    temp_c = to_number(celsius, "题1", "celsius")
    zero_c = to_number(absolute_zero_c, "题1", "absolute_zero_c")
    if temp_c < zero_c:
        raise ExerciseError("题1", "低于绝对零度", celsius=temp_c,
                            absolute_zero_c=zero_c)
    return temp_c * 9.0 / 5.0 + 32.0, temp_c + 273.15


def temperature_level(celsius, warn, danger):
    """按阈值给温度定级（阈值来自 config/rules.yaml，非硬编码）。"""
    temp_c = to_number(celsius, "题1", "celsius")
    if temp_c >= danger:
        return LEVEL_DANGER
    if temp_c >= warn:
        return LEVEL_WARN
    return LEVEL_NORMAL


def solve_quadratic(a, b, c):
    """题2：一元二次方程；返回 (x1, x2)，无实根返回 None，重根两值相等。

    三分支：判别式 d>0 两实根、d==0 重根、d<0 无实根（返回 None）。
    数值口径：用稳定式 q=-(b+sign(b)√d)/2 再取 q/a 与 c/q，避免
    b 与 √d 相减时的"灾难性抵消"（b=-1e6、c=1 时朴素公式的小根
    误差可达 1e-6 量级——这是 A 层极值断言真实抓到的坑）。
    返回顺序保持 (-b+√d)/2a 在前、(-b-√d)/2a 在后。
    异常：a==0（退化一次方程）/空输入/非数字 → ExerciseError。
    """
    coef_a = to_number(a, "题2", "a")
    coef_b = to_number(b, "题2", "b")
    coef_c = to_number(c, "题2", "c")
    if coef_a == 0.0:
        raise ExerciseError("题2", "a=0 不是二次方程", a=coef_a)
    disc = coef_b * coef_b - 4.0 * coef_a * coef_c
    if disc < 0.0:
        return None
    root = math.sqrt(disc)
    q = -0.5 * (coef_b + math.copysign(root, coef_b if coef_b else 1.0))
    minus = q / coef_a
    plus = coef_c / q if q != 0.0 else (-coef_b + root) / (2.0 * coef_a)
    if coef_b >= 0.0:
        return plus, minus
    return minus, plus


def normalize_id(value, width=2):
    """设备 ID 归一化为零填充字符串（与 config.normalize_id 同口径）。"""
    if value is None or isinstance(value, bool):
        raise ExerciseError("题3", "空/布尔设备ID", value=value)
    if not isinstance(value, (int, str)):
        raise ExerciseError("题3", "设备ID类型不支持", value=value,
                            type=type(value).__name__)
    text = str(value).strip()
    if not text:
        raise ExerciseError("题3", "空设备ID")
    size = max(1, int(width))
    if text.isdigit():
        return text.zfill(size)
    return text.upper()


class Device:
    """题4 基类：C 的 struct+函数 → Python 的"数据+行为"一体。"""

    def __init__(self, dev_id, name, status=STATUS_STOP):
        self.dev_id = normalize_id(dev_id, 2)
        if not str(name).strip():
            raise ExerciseError("题4", "设备名为空输入", name=name)
        self.name = str(name).strip()
        self.status = str(status)

    def start(self):
        """基类启动：置运行状态并返回启动描述。"""
        self.status = STATUS_RUN
        return "%s启动" % self.name

    def stop(self):
        """基类停机：回到停止状态。"""
        self.status = STATUS_STOP
        return "%s停止" % self.name

    def describe(self):
        """状态快照（报告/测试用，纯函数无副作用）。"""
        return {"dev_id": self.dev_id, "name": self.name,
                "status": self.status}

    def __repr__(self):
        return "Device(%s, %s, %s)" % (self.dev_id, self.name, self.status)


class PLC(Device):
    """题4 子类：新增 scan_ms 属性 + scan() 方法，并覆盖 start()。"""

    def __init__(self, dev_id, name, scan_ms=100, status=STATUS_STOP,
                 scan_ms_max=10000):
        super().__init__(dev_id, name, status)
        self.scan_ms = self._validate_scan_ms(scan_ms, scan_ms_max)
        self.scan_ms_max = int(scan_ms_max)
        self.scan_rounds_done = 0

    @staticmethod
    def _validate_scan_ms(scan_ms, scan_ms_max):
        """扫描周期必须是 (0, scan_ms_max] 内的整数。"""
        if scan_ms is None or isinstance(scan_ms, bool):
            raise ExerciseError("题4", "空/布尔扫描周期", scan_ms=scan_ms)
        if isinstance(scan_ms, str):
            text = scan_ms.strip()
            if not text:
                raise ExerciseError("题4", "空扫描周期字符串")
            try:
                scan_ms = int(text)
            except ValueError:
                raise ExerciseError("题4", "扫描周期必须是整数",
                                    scan_ms=scan_ms) from None
        elif isinstance(scan_ms, float):
            if not float(scan_ms).is_integer():
                raise ExerciseError("题4", "扫描周期必须是整数", scan_ms=scan_ms)
            scan_ms = int(scan_ms)
        elif not isinstance(scan_ms, int):
            raise ExerciseError("题4", "扫描周期类型不支持", scan_ms=scan_ms)
        if scan_ms <= 0:
            raise ExerciseError("题4", "扫描周期必须为正", scan_ms=scan_ms)
        if scan_ms > int(scan_ms_max):
            raise ExerciseError("题4", "扫描周期超出上限", scan_ms=scan_ms,
                                scan_ms_max=int(scan_ms_max))
        return int(scan_ms)

    def start(self):
        """覆盖基类 start()：启动同时播报扫描周期（工单要求的"含 scan"）。"""
        self.status = STATUS_RUN
        return "%s启动, 扫描%dms" % (self.name, self.scan_ms)

    def scan(self, rounds=1):
        """执行 rounds 个扫描轮次，返回每轮读数描述（确定性，无随机源）。"""
        if rounds is None or isinstance(rounds, bool):
            raise ExerciseError("题4", "空/布尔轮次", rounds=rounds)
        try:
            count = int(rounds)
        except (TypeError, ValueError):
            raise ExerciseError("题4", "轮次必须是整数", rounds=rounds) from None
        if count < 0 or count > 1000:
            raise ExerciseError("题4", "轮次越界(0~1000)", rounds=count)
        if self.status != STATUS_RUN:
            raise ExerciseError("题4", "未启动不能扫描", status=self.status)
        lines = []
        for _ in range(count):
            self.scan_rounds_done += 1
            lines.append("第%d轮扫描: %s status=%s cycle=%dms"
                         % (self.scan_rounds_done, self.name, self.status,
                            self.scan_ms))
        return lines

    def describe(self):
        """子类扩展快照：基类字段 + 扫描周期。"""
        info = super().describe()
        info["scan_ms"] = self.scan_ms
        return info

    def __repr__(self):
        return "PLC(%s, %s, %dms, %s)" % (self.dev_id, self.name,
                                          self.scan_ms, self.status)


class Registry:
    """题3：设备清单 CRUD（字典存储，O(1) 按 ID 查，键统一零填充）。"""

    def __init__(self, id_width=2, default_status=STATUS_STOP):
        self._data = {}
        self.id_width = max(1, int(id_width))
        self.default_status = str(default_status)

    def _key(self, dev_id):
        return normalize_id(dev_id, self.id_width)

    def add(self, dev_id, name, status=None, device=None):
        """增：键重复直接报错（不做静默覆盖，防"以为改了其实是新建"）。"""
        key = self._key(dev_id)
        if key in self._data:
            raise ExerciseError("题3", "设备ID已存在", dev_id=key)
        if device is not None:
            self._data[key] = device
            return device
        self._data[key] = Device(key, name, status or self.default_status)
        return self._data[key]

    def get(self, dev_id):
        """查：不存在返回 None（调用方决定是否报错）。"""
        return self._data.get(self._key(dev_id))

    def update(self, target_id, **fields):
        """改：只允许 name/status；不存在时抛 ExerciseError。

        首参改名 target_id，是为了让 dev_id=... 落到 **fields 里被
        显式拒绝（工单决策矩阵：ID 不可变），而不是撞成 TypeError。
        """
        device = self.get(target_id)
        if device is None:
            raise ExerciseError("题3", "改不存在的设备", dev_id=self._key(target_id))
        for key, value in fields.items():
            if key == "dev_id":
                raise ExerciseError("题3", "主键不可改", dev_id=str(value))
            if key not in ("name", "status"):
                raise ExerciseError("题3", "不支持修改的字段", field=key)
            if not str(value).strip():
                raise ExerciseError("题3", "空字段值", field=key, value=value)
            setattr(device, key, str(value).strip())
        return device

    def remove(self, dev_id):
        """删：真正弹出键；不存在返回 None（不静默"假装删除"）。"""
        return self._data.pop(self._key(dev_id), None)

    def count(self):
        return len(self._data)

    def ids(self):
        return sorted(self._data)

    def to_rows(self):
        """导出全部设备（按 ID 升序，报告用）。"""
        return [self._data[key].describe() for key in self.ids()]

    def top(self, k):
        """按配置 topk 取前 k 台（topk 的唯一下拉点，非死配置）。"""
        return self.to_rows()[:max(0, int(k))]


def safe_read(path, encoding="utf-8"):
    """题5：异常保护读取，按约定返回标记字符串而不是抛出崩溃。

    返回：正文 / FILE_NOT_FOUND / BAD_ENCODING / IS_DIRECTORY /
          EMPTY_PATH / READ_DENIED（权限问题）。
    纪律：用 try/except 兜错误，禁止 os.path.exists 预判（防竞态）。
    """
    if path is None:
        return EMPTY_PATH
    text = str(path).strip()
    if not text:
        return EMPTY_PATH
    try:
        with open(text, encoding=encoding) as handle:
            return handle.read()
    except FileNotFoundError:
        return FILE_NOT_FOUND
    except IsADirectoryError:
        return IS_DIRECTORY
    except PermissionError:
        return READ_DENIED
    except UnicodeDecodeError:
        return BAD_ENCODING
