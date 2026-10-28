# -*- coding: utf-8 -*-
"""存储引擎⑤ KV与缓存：Redis优先，diskcache进程外等价回退（机房离线兜底）

教学生"同一接口、两种实现"的工程决策：
  - Redis: 跨进程共享 / TTL原生 / 计数器原子INCR（限流）
  - diskcache: 纯Python落盘，零服务依赖——决策矩阵里"机房无Redis服务"时的B案
    （计数走 Cache.incr，与 Redis INCR 同为原子自增，回退后限流语义不变）
  - memory: 两级都不可用时的进程内 TTL 兜底（单进程可用，跨进程不共享——显式标注）
本模块对上层暴露统一 API: get/put/incr —— 上层不感知后端
"""
import threading
import time

from config import DISK_CACHE, REDIS_URL


class RedisKV:
    name = "redis"

    def __init__(self, url):
        import redis
        self.r = redis.Redis.from_url(url, socket_connect_timeout=1,
                                      decode_responses=True)
        self.r.ping()

    def put(self, k, v, ttl=60):
        return self.r.setex(k, ttl, v)

    def get(self, k):
        return self.r.get(k)

    def incr(self, k, ttl=3600):
        """原子计数：API限流（每IP每小时N次）"""
        n = self.r.incr(k)
        if n == 1:
            self.r.expire(k, ttl)
        return n


class DiskKV:
    name = "diskcache"

    def __init__(self, path):
        import diskcache
        self.c = diskcache.Cache(path)

    def put(self, k, v, ttl=60):
        return self.c.set(k, v, expire=ttl)

    def get(self, k):
        return self.c.get(k)

    def incr(self, k, ttl=3600):
        # Cache.incr 是原子操作（旧写法 get()+set() 是读-改-写，并发下会少计几次）；
        # 仅首次计数时设 TTL，与 Redis "INCR==1 才 EXPIRE" 的固定窗口语义一致
        n = self.c.incr(k, default=0)
        if n == 1:
            self.c.touch(k, expire=ttl)
        return n


class MemoryKV:
    """进程内 TTL 兜底：无 Redis、无 diskcache 时平台仍能跑（标注为 memory）。"""

    name = "memory"

    def __init__(self):
        self._d = {}
        self._lock = threading.Lock()

    def put(self, k, v, ttl=60):
        with self._lock:
            self._d[k] = (v, time.time() + ttl)

    def get(self, k):
        with self._lock:
            item = self._d.get(k)
            if not item:
                return None
            if item[1] < time.time():
                del self._d[k]
                return None
            return item[0]

    def incr(self, k, ttl=3600):
        with self._lock:
            v, exp = self._d.get(k, (0, time.time() + ttl))
            if exp < time.time():
                v, exp = 0, time.time() + ttl
            v += 1
            self._d[k] = (v, exp)
            return v


def make_kv():
    """工厂：Redis → diskcache → memory 三级回退（每级都打印决策留痕）"""
    try:
        kv = RedisKV(REDIS_URL)
        print(f"[kv] 后端=redis ({REDIS_URL})")
        return kv
    except Exception as e:
        print(f"[kv] redis不可达({type(e).__name__})→回退diskcache: {DISK_CACHE}")
    try:
        return DiskKV(DISK_CACHE)
    except Exception as e2:                    # diskcache 也没装（极简环境）
        print(f"[kv] diskcache不可用({type(e2).__name__})→回退进程内 memory（跨进程不共享）")
        return MemoryKV()


if __name__ == "__main__":
    kv = make_kv()
    kv.put("demo:hello", f"t={time.time()}", ttl=30)
    print("读回:", kv.get("demo:hello"), "| 计数:", kv.incr("demo:cnt"))
