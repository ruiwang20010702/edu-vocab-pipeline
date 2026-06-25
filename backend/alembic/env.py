"""Alembic 迁移环境配置."""

from logging.config import fileConfig

# 确保所有模型被导入，否则 autogenerate 检测不到
import vocab_qc.core.models  # noqa: F401
from alembic import context
from sqlalchemy import engine_from_config, pool
from vocab_qc.core.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 优先使用 Settings（pydantic-settings 统一读取环境变量 + .env 文件）
from vocab_qc.core.config import settings

db_url = settings.database_url_migrate or settings.database_url_sync
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
