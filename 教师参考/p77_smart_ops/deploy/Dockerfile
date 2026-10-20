# 容器化上线（docker compose up --build 即部署）
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir litestar granian kuzu duckdb chromadb diskcache redis \
    scikit-learn joblib sqlalchemy
EXPOSE 8900
CMD ["sh", "deploy/run.sh"]
