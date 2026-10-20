# -*- coding: utf-8 -*-
"""存储引擎⑤ KV与缓存：Redis优先，diskcache进程外等价回退（机房离线兜底）

教学生"同一接口、两种实现"的工程决策：
  - Redis: 跨进程共享 / TTL原生 / 计数器原子INCR（限流）
  - diskcache: 纯Python落盘，零服务依赖——决策矩阵里"机房无Redis服务"时的B案
本模块对上层暴露统一 API: get/put/incr —— 上层不感知后端
"""
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
        n = (self.c.get(k) or 0) + 1
        self.c.set(k, n, expire=ttl)
        return n


def make_kv():
    """工厂：Redis可用用Redis，否则回退diskcache（打印决策留痕）"""
    try:
        kv = RedisKV(REDIS_URL)
        print(f"[kv] 后端=redis ({REDIS_URL})")
        return kv
    except Exception as e:
        print(f"[kv] redis不可达({type(e).__name__})→回退diskcache: {DISK_CACHE}")
        return DiskKV(DISK_CACHE)


if __name__ == "__main__":
    kv = make_kv()
    kv.put("demo:hello", f"t={time.time()}", ttl=30)
    print("读回:", kv.get("demo:hello"), "| 计数:", kv.incr("demo:cnt"))
