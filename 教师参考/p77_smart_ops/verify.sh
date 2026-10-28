#!/usr/bin/env bash
# P7 端到端验证：五库 → 模型门禁 → granian服务 → 分层断言（公开分享前必跑）
# 分层口径（对应 W09 分层工单）：
#   [1/6]-[5/6] = C层「五库段全绿」；[6/6] = B层「ALL PASS」+ D层「4个API 200」
#   末尾两条 A层留痕：跨进程检索可复现 + 压测/召回脚本存在性自检
set -e; cd "$(dirname "$0")"
# 教学环境优先级：pp03 conda 环境 > 系统 anaconda > PATH 里的 python3
if [ -z "${PY:-}" ]; then
  for c in /opt/anaconda3/envs/pp03/bin/python /opt/anaconda3/bin/python "$(command -v python3)"; do
    [ -x "$c" ] && PY="$c" && break
  done
fi
echo "[env] PY=$PY"; echo "[env] $(command -v ab >/dev/null && echo 'ab=已安装' || echo 'ab=未安装(A层压测轮跳过)')"
FAIL=0; ok(){ echo "  ✓ $1"; }; bad(){ echo "  ✗ $1"; FAIL=1; }

echo "[1/6] 关系型 SQLite(WAL)"
$PY -m stores.relational | grep -q PUMP-03 && ok 台账 || bad 台账
$PY -m stores.relational | grep -q "journal_mode = wal" && ok "WAL 已真正开启" || bad "WAL 未开启(与决策矩阵不符)"

echo "[2/6] 时序 DuckDB"
$PY -m stores.timeseries | grep -q samples && ok 窗口特征 || bad 窗口特征
$PY -c "import sys;sys.path.insert(0,'.');from stores.timeseries import window_feats;print(window_feats('NOPE-99')['samples'])" \
  | grep -q "^0$" && ok "空窗口不崩(未知设备)" || bad "空窗口未兜底"

echo "[3/6] 图 Kùzu"
$PY -m stores.graph | grep -q MOTOR-A2-1 && ok 影响路径 || bad 影响路径
$PY -c "import sys;sys.path.insert(0,'.');from stores.graph import impact_path;print(','.join(impact_path('PUMP-03')['affected_lines']))" \
  | grep -q LINE-A2 && ok "波及产线可解释" || bad 波及产线未输出

echo "[4/6] 向量 Chroma（跨进程可复现）"
$PY -m stores.vector_store | grep -q case && ok 语义检索 || bad 语义检索
# 只比"命中文本+距离"的稳定投影（metadata 的 dict 顺序在不同进程可能不同，不参与判定）
VS='import sys,json;sys.path.insert(0,".");from stores.vector_store import search;'
VS+='print(json.dumps([[x["case"],x["dist"]] for x in search("泵振动持续变大怎么办",2)],ensure_ascii=False,sort_keys=True))'
H1=$($PY -c "$VS"); H2=$($PY -c "$VS")
[ "$H1" = "$H2" ] && ok "播种/检索跨进程一致(PYTHONHASHSEED 无关)" || bad "嵌入不稳定：两次进程结果不同"

echo "[5/6] 诊断模型（F1 门禁）"
$PY train_model.py | grep -q "F1" && ok 诊断模型 || bad 诊断模型

echo "[6/6] HTTP 服务（granian + Litestar）"
if ! $PY -c "import granian, litestar" 2>/dev/null; then
  bad "granian/litestar 未安装 → D/B 层 HTTP 断言无法执行（先 pip install litestar granian）"
else
  pkill -f "granian.*:app" 2>/dev/null || true; sleep 1
  (REDIS_URL=${REDIS_URL:-redis://127.0.0.1:6399/0} $PY -m granian --interface asgi service.app:app \
    --host 127.0.0.1 --port 8900 >/tmp/granian_v.log 2>&1 &); sleep 5
  curl -s localhost:8900/health | grep -q '"ok":true' && ok /health || bad /health
  curl -s localhost:8900/api/device/PUMP-03 | grep -q LINE-A2 && ok 设备360° || bad 设备360°
  curl -s -X POST localhost:8900/api/predict -H 'Content-Type: application/json' \
    -d '{"device":"PUMP-03"}' | grep -q proba_wear && ok 模型推理 || bad 模型推理
  curl -s -X POST localhost:8900/api/predict -H 'Content-Type: application/json' \
    -d '{"device":"PUMP-03"}' | grep -q '"cache": *"HIT"' && ok "缓存命中 MISS→HIT" || bad 缓存未命中
  # 注意 ${DEV} 必须带花括号：裸写 $DEV振动 时，非 UTF-8 locale 下 bash 会把
  # "振"的首字节并入变量名 → 请求体里出现残缺 UTF-8 → 服务端 400，看着像"智能体挂了"
  for DEV in PUMP-03 FAN-02; do
    curl -s -X POST localhost:8900/api/agent/ask -H 'Content-Type: application/json' \
      -H "x-client: verify-${DEV}" \
      -d "{\"question\":\"${DEV}振动变大，影响哪些产线？以前怎么处理？\"}" \
      | grep -q '"suggest_action"' && ok "智能体取证(${DEV})" || bad "智能体诊断(${DEV})"
  done
  for EP in /api/device/NOPE-99; do
    code=$(curl -s -o /dev/null -w '%{http_code}' localhost:8900$EP)
    [ "$code" == "404" ] && ok "未知设备返回404(非500)" || bad "未知设备返回 $code(应 404)"
  done
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST localhost:8900/api/agent/ask \
    -H 'Content-Type: application/json' -d '{"question":""}')
  [ "$code" == "400" ] && ok "空问题返回400(非500)" || bad "空问题返回 $code(应 400)"
  pkill -f "granian.*:app" || true
fi

echo "[A/·] 拓展层脚本自检"
[ -f eval_retrieval.py ] && $PY eval_retrieval.py --k 2 | grep -q "recall@2" && ok "召回对比(hash↔bge)" || bad 召回对比脚本
[ -f loadtest.py ] && ok "workers 压测脚本(loadtest.py)" || bad 压测脚本缺失

[ $FAIL -eq 0 ] && echo "ALL PASS ✅" || { echo "存在失败项 ❌"; exit 1; }
