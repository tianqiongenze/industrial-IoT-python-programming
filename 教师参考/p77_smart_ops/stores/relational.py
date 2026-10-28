# -*- coding: utf-8 -*-
"""存储引擎① 关系型：SQLAlchemy 2.0 + SQLite（WAL）——设备台账/测点/告警单

决策矩阵口径落地的两处细节（教师版已实证，学生版易只写不验）：
  · WAL 不是"连上就有"——SQLite 默认 journal_mode=delete，必须显式 PRAGMA 打开，
    否则 README 里"SQLite(WAL) 支撑大屏轮询读写并发"就是一句空话；
  · 时间戳取 config.AS_OF 而非 utcnow()，保证播种可复现。

单独运行: /opt/anaconda3/envs/pp03/bin/python -m stores.relational
"""
from datetime import datetime

from sqlalchemy import (JSON, Column, DateTime, ForeignKey, Integer,
                        String, create_engine, event, select)
from sqlalchemy.orm import DeclarativeBase, Session, relationship

from config import AS_OF, SQLITE_URL


class Base(DeclarativeBase):
    pass


class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True)
    code = Column(String(16), unique=True)
    name = Column(String(64))
    line_code = Column(String(16))          # 所属产线（与图库拓扑同源）
    installed = Column(DateTime, default=datetime(2024, 3, 1))
    points = relationship("SensorPoint", back_populates="device",
                          order_by="SensorPoint.id")   # 显式排序：输出可复现
    alerts = relationship("Alert", back_populates="device", order_by="Alert.id")


class SensorPoint(Base):
    __tablename__ = "sensor_points"
    id = Column(Integer, primary_key=True)
    device_id = Column(ForeignKey("devices.id"))
    tag = Column(String(32))                # 如 vib_rms / temp
    unit = Column(String(8), default="mm/s")
    device = relationship("Device", back_populates="points")


# 测点单位必须按物理量给（ vib_rms=mm/s、pressure=MPa、temp=℃ ）：
# 早期版本所有测点都吃默认值 mm/s，设备360°视图里"压力 7.8 mm/s"这类单位错误
# 在真实运维现场是致命误导（量纲错→阈值错→告警错），故播种时显式带单位。
TAG_UNITS = {"vib_rms": "mm/s", "pressure": "MPa", "temp": "℃"}


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    device_id = Column(ForeignKey("devices.id"))
    ts = Column(DateTime, default=AS_OF)    # 固定口径时点（可复现）
    level = Column(String(8))               # warn / alarm
    detail = Column(JSON)                   # 半结构化明细（JSON列=文档型用法）
    device = relationship("Device", back_populates="alerts")


def _engine(url=SQLITE_URL):
    """建引擎并**真正**打开 WAL：每个连接执行 PRAGMA（journal_mode 是库级持久设置）。"""
    eng = create_engine(url, connect_args={"timeout": 15})

    @event.listens_for(eng, "connect")
    def _set_pragma(dbapi_conn, _rec):      # SQLAlchemy 连接期钩子：并发读写不互锁
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=15000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    return eng


def journal_mode(url=SQLITE_URL) -> str:
    """自检：返回当前库的 journal_mode（教学断言用，应为 'wal'）。"""
    from sqlalchemy import text
    with _engine(url).connect() as c:
        return str(c.execute(text("PRAGMA journal_mode")).scalar())


def build_seed():
    eng = _engine()
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        pump3 = Device(code="PUMP-03", name="3号泵站循环泵", line_code="LINE-A2")
        fan2 = Device(code="FAN-02", name="2号主风机", line_code="LINE-B1")
        s.add_all([pump3, fan2])
        for d, tags in ((pump3, ["vib_rms", "pressure", "temp"]),
                        (fan2, ["vib_rms", "temp"])):
            for t in tags:
                d.points.append(SensorPoint(tag=t, unit=TAG_UNITS[t]))
        pump3.alerts.append(Alert(level="warn", detail={"vib_rms": 7.8, "msg": "振动连续3日爬升"}))
        s.commit()
    return eng


def device_profile(code: str) -> dict:
    """设备360°视图：台账 + 测点 + 近期告警（服务层 /api/device/{code} 数据源）

    工单点位 P7-1 答案要点：select(Device).where(Device.code == code) → 组装 dict；
    查无设备返回带 error 键的字典（服务层据此回 404，而不是把 None 拼进 f-string 崩 500）。
    """
    eng = _engine()
    with Session(eng) as s:
        d = s.scalar(select(Device).where(Device.code == code))
        if not d:
            return {"error": f"设备{code}不存在", "code": code}
        return {
            "code": d.code, "name": d.name, "line": d.line_code,
            "installed": d.installed.strftime("%Y-%m-%d") if d.installed else None,
            "points": [{"tag": p.tag, "unit": p.unit} for p in d.points],
            "alerts": [{"level": a.level, "ts": str(a.ts), "detail": a.detail}
                       for a in d.alerts],
        }


if __name__ == "__main__":
    build_seed()
    import json
    print("[wal] journal_mode =", journal_mode())
    print(json.dumps(device_profile("PUMP-03"), ensure_ascii=False, indent=1))
