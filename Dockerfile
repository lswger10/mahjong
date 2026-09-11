# ── 麻将游戏 (Mahjong) — Cloud Run Dockerfile ──────────────────────────────
# 单阶段构建：FastAPI + Uvicorn，同时 serve 前端静态文件
# Cloud Run 默认监听 PORT 环境变量（默认 8080）
# ---------------------------------------------------------------------------

FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip tini ca-certificates \
    && curl -fsSL https://github.com/openai/tunnel-client/releases/download/v0.0.14/tunnel-client-v0.0.14-linux-amd64.zip -o /tmp/tunnel.zip \
    && echo '15bd17e805cad39d412199115bb9e10a978dd35258a114cdf25dd2ae6681c7d3  /tmp/tunnel.zip' | sha256sum -c - \
    && mkdir /opt/tunnel-client && unzip -q /tmp/tunnel.zip -d /opt/tunnel-client \
    && rm /tmp/tunnel.zip && rm -rf /var/lib/apt/lists/*
ENV PATH="/opt/tunnel-client:${PATH}"
RUN tunnel-client --version && cloudflared --version

# 不生成 .pyc 文件；关闭 Python 输出缓冲（日志实时可见）
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先复制 requirements 利用 Docker layer cache
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# 复制后端源码
COPY backend/ ./backend/

# 复制前端静态文件（FastAPI 通过 StaticFiles 挂载）
COPY frontend/ ./frontend/

# Cloud Run 会注入 PORT 环境变量（默认 8080）
# uvicorn 从 /app 目录以 backend.main:app 方式启动
COPY scripts/start-container.sh scripts/test-container.sh ./scripts/
RUN bash -n scripts/start-container.sh && bash scripts/test-container.sh
ENV MAHJONG_DATA_DIR=/data/mahjong
EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "-g", "--"]
CMD ["bash", "scripts/start-container.sh"]
