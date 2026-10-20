# -*- coding: utf-8 -*-
# [教学脚手架] 下列导入/变量供 TODO 完成后使用，故标注 noqa 而非删除
"""P5 产线数据仓库与ORM —— 框架(SQLAlchemy+SQLite)
数据: 自动模拟(P4 buffer.db存在则可直接导入, 见 TODO-5)
"""
from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey,  # noqa: F401
                        Integer, String, create_engine, func, select)
from sqlalchemy.orm import DeclarativeBase, Session, relationship

DB = "sqlite:///warehouse.db"


class Base(DeclarativeBase):
    pass


class Device(Base):
    """设备表"""
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True)
    code = Column(String(16), unique=True, nullable=False)
    name = Column(String(64))
    points = relationship("SensorPoint", back_populates="device")

    # TODO-1: 补充 area(车间) 字段


class SensorPoint(Base):
    """测点表(设备↔测点 一对多)"""
    __tablename__ = "points"
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id"))
    metric = Column(String(16))          # temp / vib / press
    unit = Column(String(8))
    device = relationship("Device", back_populates="points")


class Record(Base):
    """采集记录表(高频写入, 索引优化重点)"""
    __tablename__ = "records"
    id = Column(Integer, primary_key=True)
    point_id = Column(Integer, ForeignKey("points.id"))
    ts = Column(DateTime, default=datetime.utcnow)
    value = Column(Float)
    # TODO-2: 联合索引 Index('idx_dev_ts', point_id, ts)


class AlarmEvent(Base):
    """告警事件表"""
    __tablename__ = "alarms"
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id"))
    ts = Column(DateTime, default=datetime.utcnow)
    level = Column(Integer)
    message = Column(String(128))
    resolved = Column(Boolean, default=False)


def init_and_seed():
    e = create_engine(DB, echo=False)
    Base.metadata.drop_all(e)
    Base.metadata.create_all(e)
    with Session(e) as s:  # noqa: F841
        # TODO-3: 种子数据: 3设备×各2测点 + 模拟记录500条(vib随机, 5%>4.5触发告警)
        # 提示: s.add_all([...]); s.commit() 批量用 s.bulk_save_objects
        pass
    return e


def queries(e):
    with Session(e) as s:  # noqa: F841
        # TODO-4a: 各设备平均vib (JOIN+GROUP BY → func.avg)
        # TODO-4b: 告警Top3设备
        # TODO-4c: 按小时聚合记录数(func.date_trunc不可用→strftime)
        pass


def optimize(e):
    """TODO-5: 加索引前后查询耗时对比(EXPLAIN QUERY PLAN via raw sql)"""
    import time
    with e.connect() as c:
        t0 = time.time()
        rows = c.execute(select(Record).where(
            Record.point_id == 1).limit(200)).fetchall()
        print("无索引耗时 %.2fms, %d行" % ((time.time() - t0) * 1000, len(rows)))
        # c.execute(text("EXPLAIN QUERY PLAN SELECT ..."))  # 查看是否SCAN
        # c.execute(text("CREATE INDEX idx_pt_ts ON records(point_id, ts)"))
        # 再测一次对比 → 写入工单


if __name__ == "__main__":
    e = init_and_seed()
    queries(e)
    optimize(e)
