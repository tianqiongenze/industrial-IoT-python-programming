#!/usr/bin/env bash
# P7 智能运维平台 一键部署（Rust运行时granian，多worker拉满CPU）
set -e
cd "$(dirname "$0")/.."
# 解释器解析：显式 PY > pp03 conda 环境 > 系统 anaconda > PATH 中 python3
# （容器里 /opt/anaconda3 不存在，旧写死路径会让 D 层"一键跑通"直接翻车）
if [ -z "${PY:-}" ]; then
  for c in /opt/anaconda3/envs/pp03/bin/python /opt/anaconda3/bin/python "$(command -v python3)"; do
    [ -x "$c" ] && PY="$c" && break
  done
fi
echo "[deploy] PY=$PY"
$PY -m stores.relational  >/dev/null   # ①建库播种（幂等）
$PY -m stores.timeseries  >/dev/null   # ②
$PY -m stores.graph       >/dev/null   # ③
$PY -m stores.vector_store >/dev/null  # ④
$PY train_model.py                    # ⑤模型（F1 门禁不达标即非零退出）
echo "[deploy] 五库+模型就绪 → granian 启动"
exec $PY -m granian --interface asgi "service.app:app" \
     --host "${HOST:-127.0.0.1}" --port "${PORT:-8900}" --workers "${WORKERS:-2}"
