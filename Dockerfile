# --- 后端 ---
FROM python:3.12-slim AS backend

WORKDIR /app

# P-M3: 先安装依赖（利用 Docker 层缓存，源码改动不会重装依赖）
COPY pyproject.toml ./
RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir $(python -c "import tomllib; deps=tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']; print(' '.join(deps))")

# 再复制源码并安装项目本身（仅注册入口点，依赖已缓存）
COPY backend/ backend/
COPY alembic.ini ./
COPY docs/prompts/ docs/prompts/
RUN pip install --no-cache-dir --no-deps .

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

ENV PYTHONPATH=backend
EXPOSE 8000
CMD ["uvicorn", "vocab_qc.api.main:app", "--host", "0.0.0.0", "--port", "8000"]


# --- 前端 ---
FROM node:20-slim AS frontend-build

WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM nginx:alpine AS frontend

COPY --from=frontend-build /app/dist /usr/share/nginx/html
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
