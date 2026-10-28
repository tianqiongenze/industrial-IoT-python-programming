# 容器化上线（docker compose up --build 即部署）
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PY=python3
COPY . .
RUN pip install --no-cache-dir litestar granian kuzu duckdb chromadb diskcache redis \
    scikit-learn joblib sqlalchemy numpy pandas pytest
EXPOSE 8900
# run.sh 里按 PY→pp03→anaconda→python3 顺序解析解释器；容器内显式给 PY
CMD ["bash", "-c", "bash deploy/run.sh"]
