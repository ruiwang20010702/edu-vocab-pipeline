# gaea/Dockerfile
# 构建命令（从项目根目录执行）：
#   docker build -f gaea/Dockerfile -t s9-vocab:gaea .
#
# 架构：单容器，s6-overlay v3 督管 nginx + gunicorn
#   migrate (oneshot) → backend (longrun, :8000 localhost)
#                     → nginx-svc (longrun, :80 对外)

# ── Stage 1: 构建前端静态资源 ─────────────────────────────────────────────────
FROM node:20-slim AS frontend-build

WORKDIR /app
COPY frontend/package*.json ./
RUN UV_THREADPOOL_SIZE=1 NODE_OPTIONS="--v8-pool-size=1" npm ci
COPY frontend/ ./
RUN UV_THREADPOOL_SIZE=1 NODE_OPTIONS="--v8-pool-size=1" npm run build


# ── Stage 2: 最终镜像（Python + nginx + s6-overlay）──────────────────────────
FROM python:3.12-slim

# ── 系统依赖 ──────────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        nginx \
        curl \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

# ── 安装 s6-overlay（自动识别 amd64 / arm64）─────────────────────────────────
# s6-overlay version
ARG S6_OVERLAY_VERSION=3.1.6.2
ENV GAEA_BASE_URL="https://flow.51talk.biz/pkg/ci/files/files"
# Install s6-overlay

ADD ${GAEA_BASE_URL}/s6-overlay-noarch/${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz /tmp/
ADD ${GAEA_BASE_URL}/s6-overlay-x86_64/${S6_OVERLAY_VERSION}/s6-overlay-x86_64.tar.xz /tmp/
RUN tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz \
    && tar -C / -Jxpf /tmp/s6-overlay-x86_64.tar.xz \
    && rm /tmp/s6-overlay-*.tar.xz

# ── Python 依赖（先装依赖，利用层缓存）───────────────────────────────────────
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir \
        $(python -c "import tomllib; d=tomllib.load(open('pyproject.toml','rb')); print(' '.join(d['project']['dependencies']))") \
        gunicorn

# ── 后端源码 ─────────────────────────────────────────────────────────────────
COPY backend/ backend/
COPY alembic.ini ./
COPY docs/prompts/ docs/prompts/
RUN pip install --no-cache-dir --no-deps .

# ── 前端静态资源 ─────────────────────────────────────────────────────────────
COPY --from=frontend-build /app/dist /usr/share/nginx/html

# ── Nginx 配置（单容器版：proxy_pass 指向 127.0.0.1:8000）───────────────────
RUN rm -f /etc/nginx/sites-enabled/default
COPY gaea/nginx.conf /etc/nginx/conf.d/default.conf

# ── s6-overlay 服务定义 ───────────────────────────────────────────────────────
COPY gaea/s6-overlay/ /etc/s6-overlay/
RUN chmod +x \
        /etc/s6-overlay/s6-rc.d/migrate/up \
        /etc/s6-overlay/s6-rc.d/backend/run \
        /etc/s6-overlay/s6-rc.d/nginx-svc/run

ENV PYTHONPATH=backend

EXPOSE 80

# s6-overlay 入口
ENTRYPOINT ["/init"]
