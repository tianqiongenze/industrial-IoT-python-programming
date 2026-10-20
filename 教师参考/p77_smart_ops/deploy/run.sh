#!/usr/bin/env bash
# P7 智能运维平台 一键部署（Rust运行时granian，多worker拉满CPU）
set -e
cd "$(dirname "$0")/.."
PY=${PY:-/opt/anaconda3/bin/python}
$PY -m stores.relational  >/dev/null   # ①建库播种（幂等）
$PY -m stores.timeseries  >/dev/null   # ②
$PY -m stores.graph       >/dev/null   # ③
$PY -m stores.vector_store >/dev/null  # ④
$PY train_model.py                    # ⑤模型
echo "[deploy] 五库+模型就绪 → granian 启动"
exec $PY -m granian --interface asgi "service.app:app" \
     --host "${HOST:-127.0.0.1}" --port "${PORT:-8900}" --workers "${WORKERS:-2}"
