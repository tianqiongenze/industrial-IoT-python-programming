#!/usr/bin/env bash
# P7 端到端验证：五库 → 模型 → granian服务 → 4组断言（公开分享前必跑）
set -e; cd "$(dirname "$0")"; PY=${PY:-/opt/anaconda3/bin/python}
FAIL=0; ok(){ echo "  ✓ $1"; }; bad(){ echo "  ✗ $1"; FAIL=1; }
echo "[1/5] 关系型"; $PY -m stores.relational | grep -q PUMP-03 && ok 台账 || bad 台账
echo "[2/5] 时序DuckDB"; $PY -m stores.timeseries | grep -q samples && ok 窗口特征 || bad 窗口特征
echo "[3/5] 图Kùzu"; $PY -m stores.graph | grep -q MOTOR-A2-1 && ok 影响路径 || bad 影响路径
echo "[4/5] 向量Chroma"; $PY -m stores.vector_store | grep -q case && ok 语义检索 || bad 语义检索
$PY train_model.py | grep -q "F1" && ok 诊断模型 || bad 诊断模型
echo "[5/5] HTTP服务"
pkill -f "granian.*:app" 2>/dev/null || true; sleep 1
(REDIS_URL=${REDIS_URL:-redis://127.0.0.1:6399/0} $PY -m granian --interface asgi service.app:app \
  --host 127.0.0.1 --port 8900 >/tmp/granian_v.log 2>&1 &); sleep 5
curl -s localhost:8900/health | grep -q '"ok":true' && ok /health || bad /health
curl -s localhost:8900/api/device/PUMP-03 | grep -q LINE-A2 && ok 设备360° || bad 设备360°
curl -s -X POST localhost:8900/api/predict -H 'Content-Type: application/json' \
  -d '{"device":"PUMP-03"}' | grep -q proba_wear && ok 模型推理 || bad 模型推理
curl -s -X POST localhost:8900/api/agent/ask -H 'Content-Type: application/json' -H 'x-client: verify' \
  -d '{"question":"PUMP-03振动变大，影响哪些产线？以前怎么处理？"}' \
  | grep -q '"suggest_action"' && ok 智能体诊断 || bad 智能体诊断
pkill -f "granian.*:app" || true
[ $FAIL -eq 0 ] && echo "ALL PASS ✅" || { echo "存在失败项 ❌"; exit 1; }
