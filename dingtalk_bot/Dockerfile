FROM python:3.11-slim

WORKDIR /app

# 先装依赖（利用层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码与知识库（.dockerignore 已排除 .env / .venv / 测试 / 缓存）
COPY . .

# Stream 模式：容器主动外拨连钉钉，无需暴露端口。
# 凭证通过运行时环境变量注入（docker run --env-file 或 compose environment），不打进镜像。
CMD ["python", "stream_client.py"]
