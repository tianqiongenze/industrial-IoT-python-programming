# -*- coding: utf-8 -*-
"""存储引擎③ 图数据库：Kùzu（嵌入式，像"图界的SQLite"，原生Cypher）

拓扑: (厂区)-[:有产线]->(产线)-[:有设备]->(设备)-[:有测点]->(测点)
      (设备)-[:上游供电]->(设备)     # 联动关系：泵停→主机联锁
价值: 关系库要写多层自连接的"影响路径"，图库一句Cypher直达
     MATCH (d:设备)-[:有设备*0..3]-(x) RETURN —— 停3号泵要联动停哪些线？

单独运行: /opt/anaconda3/bin/python -m stores.graph
"""
import kuzu

from config import KUZU_DIR

SCHEMA = [
    "CREATE NODE TABLE 厂区(id STRING, name STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE 产线(id STRING, name STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE 设备(id STRING, name STRING, state STRING, PRIMARY KEY(id))",
    "CREATE REL TABLE 有产线(FROM 厂区 TO 产线)",
    "CREATE REL TABLE 有设备(FROM 产线 TO 设备)",
    "CREATE REL TABLE 有测点(FROM 设备 TO 产线)",  # 占位反向边（演示多跳）
    "CREATE REL TABLE 上游供电(FROM 设备 TO 设备)",
]


def seed():
    db, con = kuzu.Database(KUZU_DIR), None
    con = kuzu.Connection(db)
    for ddl in SCHEMA:
        con.execute(ddl)
    rows = [("CREATE (:厂区 {id:'P1', name:'两江智造一号厂区'})"),
            ("CREATE (:产线 {id:'LINE-A2', name:'精加工A2线'})"),
            ("CREATE (:产线 {id:'LINE-B1', name:'装配B1线'})"),
            ("CREATE (:设备 {id:'PUMP-03', name:'3号泵站循环泵', state:'warn'})"),
            ("CREATE (:设备 {id:'MOTOR-A2-1', name:'A2线主电机', state:'ok'})"),
            ("CREATE (:设备 {id:'FAN-02', name:'2号主风机', state:'ok'})"),
            ("MATCH (a:厂区{id:'P1'}), (b:产线{id:'LINE-A2'}) CREATE (a)-[:有产线]->(b)"),
            ("MATCH (a:厂区{id:'P1'}), (b:产线{id:'LINE-B1'}) CREATE (a)-[:有产线]->(b)"),
            ("MATCH (l:产线{id:'LINE-A2'}), (d:设备{id:'PUMP-03'}) CREATE (l)-[:有设备]->(d)"),
            ("MATCH (l:产线{id:'LINE-A2'}), (d:设备{id:'MOTOR-A2-1'}) CREATE (l)-[:有设备]->(d)"),
            ("MATCH (l:产线{id:'LINE-B1'}), (d:设备{id:'FAN-02'}) CREATE (l)-[:有设备]->(d)"),
            ("MATCH (a:设备{id:'PUMP-03'}), (b:设备{id:'MOTOR-A2-1'}) "
             "CREATE (a)-[:上游供电]->(b)")]
    for r in rows:
        con.execute(r)
    con.close()
    return db


def impact_path(device_id: str) -> dict:
    """影响路径分析：该设备异常会波及哪些产线/上下游设备（运维决策核心查询）"""
    db = kuzu.Database(KUZU_DIR, read_only=True)
    con = kuzu.Connection(db)
    # TODO-P7-3: Cypher两跳——(设备)-[:上游供电]->(下游设备)<-[:有设备]-(产线)
    #   提示: res = con.execute("MATCH ... RETURN down.id, down.name, line.id, line.name")
    res = con.execute(f"""
        MATCH (d:设备 {{id: '{device_id}'}}) RETURN d.id
    """)
    hits = []
    while res.has_next():
        row = res.get_next()
        hits.append({"downstream": row[0], "down_name": row[1],
                     "line": row[2], "line_name": row[3]})
    lines = con.execute(f"""
        MATCH (l:产线)-[:有设备]->(d:设备 {{id: '{device_id}'}}) RETURN l.id, l.name
    """)
    own = [lines.get_next()[0] for _ in range(lines.get_num_tuples())]
    con.close()
    return {"device": device_id, "own_lines": own,
            "collateral": hits}


if __name__ == "__main__":
    import json
    import shutil
    import os
    if os.path.isdir(KUZU_DIR):
        shutil.rmtree(KUZU_DIR)          # 演示可重复（0.11为单文件库，两种都兼容）
    elif os.path.exists(KUZU_DIR):
        os.remove(KUZU_DIR)
    seed()
    print(json.dumps(impact_path("PUMP-03"), ensure_ascii=False, indent=1))
