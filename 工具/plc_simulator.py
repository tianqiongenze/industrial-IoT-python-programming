# -*- coding: utf-8 -*-
"""
多PLC模拟器一键启动（W6 P4.1多源采集用; 兼容02包mini_modbus_server协议）
v3.1: 内置"2号PLC自动掉线"守护——无需人工干预, 每45~90秒随机掉线5秒后自动重启,
      供断线重连教学实测(学生端看到ConnectionRefused/超时即为考点)。
用法:  python plc_simulator.py            # 三台PLC + 2号随机掉线守护
       python plc_simulator.py --stable   # 三台全部稳定(联调模式, 不掉线)
       python plc_simulator.py --check    # 快速连通自测
"""
import random
import socket
import struct
import subprocess
import sys
import time

BASE = __file__.rsplit("/", 2)[0]
MODBUS = BASE + "/../02-程序设计基础/虚拟产线/mini_modbus_server.py"
PLCS = [(5020, 1), (5021, 2), (5022, 3)]


def spawn(port, unit):
    return subprocess.Popen([sys.executable, MODBUS, str(port), str(unit)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def flaky_daemon(proc_2):
    """2号PLC(5021)随机掉线5秒(v3.1自动化)"""
    rng = random.Random(2026)
    while True:
        time.sleep(rng.uniform(45, 90))
        print("[守护] PLC#2(5021) 掉线 5s —— 学生端应触发重连逻辑", flush=True)
        proc_2.terminate()
        proc_2.wait(timeout=3)
        time.sleep(5)
        proc_2 = spawn(5021, 2)
        print("[守护] PLC#2(5021) 已重启", flush=True)


def start_all(stable=False):
    procs = {port: spawn(port, unit) for port, unit in PLCS}
    for port, unit in PLCS:
        print(f"PLC#{unit} -> 127.0.0.1:{port}")
    if not stable:
        print("2号PLC(5021)自动掉线守护已启用: 每45~90秒掉线5秒自动恢复")
        import threading
        threading.Thread(target=flaky_daemon, args=(procs[5021],),
                         daemon=True).start()
    else:
        print("稳定模式(--stable): 三台PLC持续在线")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        for p in procs.values():
            p.terminate()


def check():
    for port in (5020, 5021, 5022):
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=2)
            pdu = struct.pack(">BHH", 3, 2, 1)
            s.sendall(struct.pack(">HHHB", 1, 0, 6, 1) + pdu)
            r = s.recv(32)
            vib = struct.unpack(">H", r[9:11])[0] / 10
            print(f"port {port}: 振动 {vib} mm/s ✓")
            s.close()
        except OSError as e:
            print(f"port {port}: 连接失败 {e} ✗")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        start_all(stable="--stable" in sys.argv)
