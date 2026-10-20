# -*- coding: utf-8 -*-
"""P6 故障诊断模型与推理服务 —— 框架
P6.1: 复用p22特征(或自动合成) → 训练→评估→保存
P6.2: http.server推理服务 + 预训练模型包(教师提供, data/models/)
运行: python W08_ml_service.py train      # 训练+评估
     python W08_ml_service.py serve       # 启动推理服务(端口8899)
     curl -X POST localhost:8899/predict -d '{"features":[...30个数]}'
"""
import json
import sys

MODEL_FILE = "model_v1.joblib"


def train():
    """P6.1 五步流"""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import classification_report, f1_score
    from sklearn.model_selection import GridSearchCV, train_test_split

    X, y = make_data()                        # 合成或读P2.2产物
    Xtr, Xte, ytr, yte = train_test_split(X, y, stratify=y, random_state=42)

    models = {"LR": LogisticRegression(max_iter=1000),
              "RF": RandomForestClassifier(random_state=42)}
    for name, m in models.items():            # 决策矩阵: 二选一并记录理由
        m.fit(Xtr, ytr)
        print(name, "F1=", f1_score(yte, m.predict(Xte), average="macro"))

    gs = GridSearchCV(RandomForestClassifier(random_state=42),
                      {"n_estimators": [50, 100, 200],
                       "max_depth": [4, 6, None]}, cv=5)
    gs.fit(Xtr, ytr)
    print(classification_report(yte, gs.predict(Xte)))
    import joblib
    joblib.dump(gs.best_estimator_, MODEL_FILE, compress=3)
    print("已保存", MODEL_FILE, gs.best_params_)


def make_data(n=400):
    """合成30维特征(0正常/1磨损): 磨损类时域/频域特征整体抬升"""
    import numpy as np
    rng = np.random.RandomState(7)
    X = rng.normal(0, 1, (n, 30))
    y = rng.binomial(1, 0.5, n)                 # 0正常 1磨损
    X[y == 1, 2:8] += rng.uniform(0.8, 1.6)     # 磨损样本第3-8维抬升
    return X, y


def serve():
    """P6.2 最小推理服务(方案A,教学); 生产级见文末方案B: Litestar+Granian(写决策矩阵)"""
    import joblib
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    model = joblib.load(MODEL_FILE)

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/predict":
                self.send_error(404)
                return
            try:
                body = json.loads(self.rfile.read(
                    int(self.headers["Content-Length"])))
                feats = body["features"]
                assert len(feats) == 30
                pred = int(model.predict([feats])[0])
                out = {"prediction": pred,
                       "label": "磨损" if pred else "正常",
                       "model": MODEL_FILE}
                code, payload = 200, out
            except Exception as exc:
                import sys
                print("[ml-service] 请求错误:", exc, file=sys.stderr)  # 详情进日志
                code, payload = 400, {"error": "bad request: 需JSON含30维features"}
            data = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

    print("推理服务: http://0.0.0.0:8899/predict (POST 30维特征)")
    print("安全提示: 监听0.0.0.0仅供机房局域网教学使用, 切勿暴露到公网")
    ThreadingHTTPServer(("0.0.0.0", 8899), H).serve_forever()


if __name__ == "__main__":
    {"train": train, "serve": serve}[sys.argv[1] if len(sys.argv) > 1 else "train"]()


# ============ P6.2 方案B：Litestar + Granian（生产级，全异步高吞吐） ============
def serve_litestar():
    """对比方案A(http.server)：类型安全/异步并发/OpenAPI文档开箱即用
    启动: python -m granian --interface asgi "W08_ml_service:app" --port 8898
    B层任务: 用 ab -n 500 -c 20 分别压两方案，QPS对比写入工单决策矩阵
    """
    from litestar import Litestar, get, post

    _cache = {}

    def _clf():
        import joblib
        if "m" not in _cache:                       # 懒加载：先train再serve也不迟
            _cache["m"] = joblib.load(MODEL_FILE)
        return _cache["m"]

    @get("/health")
    async def health() -> dict:
        return {"ok": True, "svc": "p66-litestar"}

    @post("/predict")
    async def predict(data: dict) -> dict:
        import numpy as np
        x = np.array(data["features"], dtype=float).reshape(1, -1)
        p = _clf().predict_proba(x)[0].tolist()
        return {"label": int(p[1] > 0.5), "proba_wear": round(p[1], 3)}

    return Litestar([health, predict], logging_config=None)


app = serve_litestar()   # granian入口：W08_ml_service:app
