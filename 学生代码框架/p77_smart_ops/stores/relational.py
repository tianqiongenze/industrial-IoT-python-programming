# -*- coding: utf-8 -*-
# [教学脚手架] 下列导入/变量供 TODO 完成后使用，故标注 noqa 而非删除
"""存储引擎① 关系型：SQLAlchemy 2.0 + SQLite（WAL）——设备台账/测点/告警单

单独运行: /opt/anaconda3/bin/python -m stores.relational
"""
from datetime import datetime

from sqlalchemy import (JSON, Column, DateTime, Float, ForeignKey, Integer,  # noqa: F401
                        String, create_engine, select)
from sqlalchemy.orm import DeclarativeBase, Session, relationship

from config import SQLITE_URL


class Base(DeclarativeBase):
    pass


class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True)
    code = Column(String(16), unique=True)
    name = Column(String(64))
    line_code = Column(String(16))          # 所属产线（与图库拓扑同源）
    installed = Column(DateTime, default=datetime(2024, 3, 1))
    points = relationship("SensorPoint", back_populates="device")
    alerts = relationship("Alert", back_populates="device")


class SensorPoint(Base):
    __tablename__ = "sensor_points"
    id = Column(Integer, primary_key=True)
    device_id = Column(ForeignKey("devices.id"))
    tag = Column(String(32))                # 如 vib_rms / temp
    unit = Column(String(8), default="mm/s")
    device = relationship("Device", back_populates="points")


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    device_id = Column(ForeignKey("devices.id"))
    ts = Column(DateTime, default=datetime.utcnow)
    level = Column(String(8))               # warn / alarm
    detail = Column(JSON)                   # 半结构化明细（JSON列=文档型用法）
    device = relationship("Device", back_populates="alerts")


def build_seed():
    eng = create_engine(SQLITE_URL, connect_args={"timeout": 15})
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        pump3 = Device(code="PUMP-03", name="3号泵站循环泵", line_code="LINE-A2")
        fan2 = Device(code="FAN-02", name="2号主风机", line_code="LINE-B1")
        s.add_all([pump3, fan2])
        for d, tags in ((pump3, ["vib_rms", "pressure", "temp"]),
                        (fan2, ["vib_rms", "temp"])):
            for t in tags:
                d.points.append(SensorPoint(tag=t))
        pump3.alerts.append(Alert(level="warn", detail={"vib_rms": 7.8, "msg": "振动连续3日爬升"}))
        s.commit()
    return eng


def device_profile(code: str) -> dict:
    """设备360°视图：台账 + 测点 + 近期告警（服务层 /api/device/{code} 数据源）"""
    # TODO-P7-1: select(Device).where(code=code) → 组装 dict
    #   提示: d.points / d.alerts 是关系属性; 完整实现见 教师参考/p77_smart_ops
    return {}


if __name__ == "__main__":
    build_seed()
    import json
    print(json.dumps(device_profile("PUMP-03"), ensure_ascii=False, indent=1))
