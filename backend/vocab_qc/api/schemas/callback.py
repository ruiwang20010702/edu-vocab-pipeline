"""AI Gateway 回调请求 Schema."""

from typing import Any

from pydantic import BaseModel


class AiTaskCallbackPayload(BaseModel):
    """Gateway 任务完成后的回调请求体."""

    task_no: str
    biz_id: str = ""
    biz_type: str = ""
    result: Any = None          # 字符串（模型输出）或 JSON 对象（完整响应）
    failed_reason: str = ""
    provider: str = ""
    status: str                 # COMPLETED / FAILED / PENDING / PROCESSING
