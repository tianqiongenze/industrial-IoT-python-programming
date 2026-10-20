# -*- coding: utf-8 -*-
"""《Python程序设计（项目实战）》 环境一键自检（python check_env.py [--deep]）"""
import sys

# ===== 解释器身份与 numpy 版本门禁（69号轮：防 PyCharm 误选旧环境）=====


def _env_guard(min_numpy=2, strict=True):
    """打印当前解释器身份；numpy 低于要求时给出 PyCharm 排障三步并（严格模式）退出"""
    exe = sys.executable.replace("\\", "/")
    env = exe.split("/envs/")[-1].split("/")[0] if "/envs/" in exe else "anaconda-base"
    print(f"[解释器] {env}  ({exe})")
    try:
        import numpy
        major = int(numpy.__version__.split(".")[0])
        if major >= min_numpy:
            print(f"[numpy  ] {numpy.__version__}  OK")
            return True
        print(f"[numpy  ] {numpy.__version__}  ✗ 需要 numpy>={min_numpy}.0")
    except ImportError:
        print(f"[numpy  ] 未安装（需要 numpy>={min_numpy}.0）")
    print("=" * 58)
    print("❗ numpy 版本异常：大概率是 PyCharm 选错了旧解释器环境。")
    print("   排障三步：")
    print("   1) PyCharm 右下角解释器 → Add New Interpreter → Conda Environment")
    print("      → 选择本课程环境（02包=py02 / 03包=pp03 / 05包=ai48）")
    print("   2) 终端执行: conda activate 课程环境名")
    print("   3) 重装依赖: pip install -r requirements.txt")
    print("   详见《软件操作指南/05-PyCharm使用指南.md》'numpy版本异常'排障一节。")
    print("=" * 58)
    if strict:
        sys.exit(1)
    return False


_env_guard(min_numpy=2, strict=True)


DEEP = "--deep" in sys.argv


def imp(mod):
    def f():
        import importlib
        m = importlib.import_module(mod)
        return getattr(m, "__version__", "ok")
    return f


def font(path):
    def f():
        import os
        assert os.path.exists(path), "缺少字体: " + path
        return "OK"
    return f


def fileexists(path):
    def f():
        import os
        assert os.path.exists(path), "缺少: " + path
        return ""
    return f


def port(host, p):
    def f():
        import socket
        s = socket.create_connection((host, p), timeout=2)
        s.close()
        return f"port {p} ✓"
    return f


ok = warn = fail = 0


def check(name, need, fn):
    global ok, warn, fail
    try:
        extra = fn() or ""
        print(f"[PASS] {name} {extra}")
        ok += 1
    except Exception as e:
        if need:
            print(f"[FAIL] {name} —— {e}")
            fail += 1
        else:
            print(f"[WARN] {name}（按周可选）—— {e}")
            warn += 1


def _py_ver():
    if sys.version_info >= (3, 12):
        return "v%d.%d" % sys.version_info[:2]
    raise RuntimeError(sys.version.split()[0])


check("Python≥3.12", True, _py_ver)
check("Git", True, lambda: __import__("subprocess").run(
    ["git", "--version"], capture_output=True, text=True).stdout.strip())


def _conda_ok():
    if "conda" in sys.executable or "envs" in sys.executable:
        return True
    raise RuntimeError(
        "当前Python路径不含 conda/envs: %s（需 conda activate pp03 后再运行）" % sys.executable)


check("conda环境(需先conda activate pp03)", True, _conda_ok)
check("pandas", True, imp("pandas"))
check("numpy", True, imp("numpy"))
check("matplotlib", False, imp("matplotlib"))
check("scikit-learn", False, imp("sklearn"))
check("joblib", False, imp("joblib"))
check("sqlalchemy", False, imp("sqlalchemy"))
check("PLC三口启动器", True, fileexists("工具/plc_simulator.py"))
if DEEP:
    for p in (5020, 5021, 5022):
        check(f"PLC:{p}", False, port("127.0.0.1", p))
print("-" * 46)
# ===== P7扩展周新栈自检（32号轮，全部离线） =====


def check_p7():
    print("\n[P7扩展周] 多模数据库+异步服务栈")
    for mod, tip in [("litestar", "pip install litestar"), ("granian", "pip install granian"),
                     ("kuzu", "图数据库"), ("duckdb", "时序OLAP"), ("chromadb", "向量库"),
                     ("diskcache", "缓存回退"), ("sklearn", "诊断模型")]:
        try:
            __import__(mod)
            print(f"[PASS] {mod} 可用")
        except ImportError:
            print(f"[WARN] {mod} 缺失 → {tip}（选做周，不装不影响P1-P6）")
    try:
        import redis
        redis.Redis.from_url("redis://127.0.0.1:6399/0", socket_connect_timeout=1).ping()
        print("[PASS] Redis服务在线(6399) → KV后端=redis")
    except Exception:
        print("[WARN] Redis不可达 → 平台自动回退diskcache（功能等价）")


check_p7()

print(f"结果: PASS {ok} | WARN {warn} | FAIL {fail}")
print("开课口径: 必需项FAIL=0 即可开课" + ("；--deep已含服务/数据连通" if DEEP else "（--deep 检查服务与数据）"))
sys.exit(1 if fail else 0)
