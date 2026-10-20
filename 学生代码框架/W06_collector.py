# -*- coding: utf-8 -*-
# [教学脚手架] 下列导入/变量供 TODO 完成后使用，故标注 noqa 而非删除
"""P4.1 多源工业数据采集系统 —— 三线程架构骨架(已给, 聚焦协议集成与可靠性)
前置: python ../工具/plc_simulator.py  (三台PLC: 5020/5021/5022)
     python ../02-Python编程基础/虚拟产线/mini_mqtt_broker.py
"""
import json  # noqa: F401
import logging
import queue
import sqlite3
import threading
import time

from pymodbus.client import ModbusTcpClient as Client  # noqa: F401
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(threadName)s %(levelname)s %(message)s")
log = logging.getLogger("collector")

PLCS = [("127.0.0.1", 5020), ("127.0.0.1", 5021), ("127.0.0.1", 5022)]
NAMES = ["temp_c", "press_mpa", "vib_mm_s", "rpm", "status"]


class ModbusCollector(threading.Thread):
    """TODO-1: 轮询三台PLC(0.5s), 读5寄存器÷10还原, 放入Queue
    可靠性: 连接失败退避重试(1s→2s→4s封顶); 2号PLC会随机掉线(实测点)"""

    def __init__(self, q: queue.Queue):
        super().__init__(daemon=True, name="Modbus")
        self.q, self.stop = q, threading.Event()
        self.stat = {"ok": 0, "fail": 0}

    def read_one(self, host, port):
        # === 你的代码: Client(host=host, port=port) → read_holding_registers(address=0, count=5) ===
        # ↑ pymodbus 3.x 必须用关键字参数（位置参数会TypeError）
        # 返回 dict(含source=f"plc@{port}") 或 None
        raise NotImplementedError

    def run(self):
        backoff = 1
        while not self.stop.is_set():
            got_any = False
            for host, port in PLCS:
                data = self.read_one(host, port)
                if data:
                    self.stat["ok"] += 1
                    self.q.put(data, timeout=1)
                    got_any = True
                else:
                    self.stat["fail"] += 1
            backoff = 1 if got_any else min(backoff * 2, 4)
            time.sleep(0.5 if got_any else backoff)


class MQTTSubscriber(threading.Thread):
    """TODO-2: 订阅 device/+/status, 消息JSON解析后放入Queue"""

    def __init__(self, q):
        super().__init__(daemon=True, name="MQTT")
        self.q = q

    def run(self):
        c = mqtt.Client()

        def on_message(_c, _u, msg):
            # === 你的代码: json.loads → dict加source="mqtt" → q.put ===
            pass

        c.on_message = on_message
        c.connect("127.0.0.1", 1883)
        c.subscribe("device/+/status", qos=0)
        c.loop_forever()


class DataProcessor(threading.Thread):
    """TODO-3: 消费Queue → 去重(同source+ts跳过) → 振动>4.5告警 → 批量入库SQLite"""

    def __init__(self, q, batch=50):
        super().__init__(daemon=True, name="Proc")
        self.q, self.batch, self.buf = q, batch, []

    def run(self):
        db = sqlite3.connect("buffer.db", check_same_thread=False)
        db.execute("CREATE TABLE IF NOT EXISTS records("
                   "source TEXT, ts REAL, temp REAL, vib REAL)")
        seen = set()  # noqa: F841
        while True:
            try:
                d = self.q.get(timeout=5)
            except queue.Empty:
                self.flush(db)
                continue
            key = (d.get("source"), round(d.get("ts", 0), 1))  # noqa: F841
            # === 你的代码: 去重/告警/入buf; len(buf)>=batch时flush ===
            self.flush(db)

    def flush(self, db):
        if self.buf:
            db.executemany("INSERT INTO records VALUES(?,?,?,?)", self.buf)
            db.commit()
            self.buf.clear()


def main():
    q = queue.Queue(maxsize=10000)
    threads = [ModbusCollector(q), MQTTSubscriber(q), DataProcessor(q)]
    for t in threads:
        t.start()
    print("采集30秒后输出统计(Ctrl+C提前结束)...")
    try:
        time.sleep(30)
    except KeyboardInterrupt:
        pass
    threads[0].stop.set()
    s = threads[0].stat
    total = s["ok"] + s["fail"]
    print(f"采集率: {s['ok']}/{total} = {s['ok'] / max(total, 1):.1%} (目标≥95%)")


if __name__ == "__main__":
    main()
