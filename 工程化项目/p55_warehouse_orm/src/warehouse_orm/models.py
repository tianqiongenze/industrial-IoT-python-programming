# -*- coding: utf-8 -*-
"""SQLAlchemy 2.x 声明式 ORM 模型：设备 / 测点 / 采集记录 / 告警事件（四表 ER）。

对应工单 P5「ER 设计 + ORM 模型」与starter任务卡 T1/T2：
  - Device.area        —— 车间字段（设备归属产线车间）
  - Device.points      —— 设备↔测点 一对多（relationship + back_populates）
  - Record             —— __table_args__ 内声明联合索引 idx_dev_ts(point_id, ts)
  - AlarmEvent         —— 告警挂设备（外键 + 级联删除显式声明）

外键约束由 SQLite 强制执行（core.make_engine 打开 PRAGMA foreign_keys），
孤儿记录（指向不存在父行的子行）会被数据库直接拒绝。
"""
from datetime import datetime, timezone

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Index,
                        Integer, String)
from sqlalchemy.orm import DeclarativeBase, relationship


def utcnow_naive():
    """统一用 UTC 去时区时间入库（工单避坑：时间戳不存字符串）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """SQLAlchemy 2.x 声明式基类（类即表、字段即列）。"""


class Device(Base):
    """设备档案表（devices）。"""

    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    code = Column(String(16), unique=True, nullable=False, comment="设备编号")
    name = Column(String(64), nullable=False, comment="设备名称")
    area = Column(String(32), nullable=False, comment="车间（设备归属产线车间）")

    points = relationship("SensorPoint", back_populates="device",
                          cascade="all, delete-orphan")
    alarms = relationship("AlarmEvent", back_populates="device",
                          cascade="all, delete-orphan")

    def __repr__(self):  # pragma: no cover - 便于调试
        return f"<Device {self.code} area={self.area}>"


class SensorPoint(Base):
    """测点表（points）：设备↔测点 一对多，metric∈{temp, vib}。"""

    __tablename__ = "points"

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    metric = Column(String(16), nullable=False, comment="测点类型 temp/vib")
    unit = Column(String(8), nullable=False, comment="工程单位")

    device = relationship("Device", back_populates="points")
    records = relationship("Record", back_populates="point",
                           cascade="all, delete-orphan")


class Record(Base):
    """采集记录表（records）：高频写入，联合索引优化重点。"""

    __tablename__ = "records"

    id = Column(Integer, primary_key=True)
    point_id = Column(Integer, ForeignKey("points.id"), nullable=False)
    ts = Column(DateTime, nullable=False, default=utcnow_naive, comment="采集时刻(UTC)")
    value = Column(Float, nullable=False, comment="测点读数")

    # 联合索引（工单 P5.2 优化项）：按测点查时段的最高频查询被完整覆盖
    __table_args__ = (Index("idx_dev_ts", "point_id", "ts"),)

    point = relationship("SensorPoint", back_populates="records")


class AlarmEvent(Base):
    """告警事件表（alarms）：告警挂设备，level 1=预警 2=停机。"""

    __tablename__ = "alarms"

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    ts = Column(DateTime, nullable=False, default=utcnow_naive)
    level = Column(Integer, nullable=False, comment="1=超预警线 2=超危险线")
    message = Column(String(128), nullable=False)
    resolved = Column(Boolean, nullable=False, default=False)

    device = relationship("Device", back_populates="alarms")


MODEL_TABLES = ("devices", "points", "records", "alarms")
