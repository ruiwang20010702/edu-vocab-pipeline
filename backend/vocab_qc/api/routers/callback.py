"""AI Gateway 回调端点: 接收异步任务完成通知."""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_db
from vocab_qc.api.schemas.callback import AiTaskCallbackPayload
from vocab_qc.core.config import settings
from vocab_qc.core.models.ai_task_queue import AiTaskQueue, AiTaskStatus
from vocab_qc.core.task_queue import TaskQueueService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/callback", tags=["回调"])


def _check_ip_whitelist(request: Request) -> None:
    """校验请求来源 IP 是否在白名单内."""
    if not settings.ai_callback_allowed_ips:
        return  # 未配置白名单则跳过（开发环境）
    client_ip = request.client.host if request.client else ""
    if client_ip not in settings.ai_callback_allowed_ips:
        logger.warning("回调 IP 不在白名单: %s", client_ip)
        raise HTTPException(status_code=403, detail="IP not allowed")


def normalize_callback_result(result: Any) -> dict:
    """将回调的 result 规范化为与轮询响应一致的格式.

    Gateway 回调的 result 可能是:
    - 完整 JSON 响应对象（含 choices/usage）→ 直接使用
    - 纯字符串（模型输出内容）→ 包装为标准 choices 格式
    """
    if isinstance(result, dict) and "choices" in result:
        return result

    # 尝试 JSON 解析字符串
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
            if isinstance(parsed, dict) and "choices" in parsed:
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

    # 包装为标准格式（usage 不可用时标记为 0）
    content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "index": 0,
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


@router.post("/ai-task")
def ai_task_callback(
    request: Request,
    payload: AiTaskCallbackPayload,
    db: Session = Depends(get_db),
) -> dict:
    """接收 Gateway 异步任务完成回调.

    幂等：同一 task_no 多次回调不会重复处理。
    """
    _check_ip_whitelist(request)

    task_no = payload.task_no
    logger.info("收到回调 task_no=%s status=%s", task_no, payload.status)

    # 查找任务
    task = db.query(AiTaskQueue).filter_by(gateway_task_no=task_no).first()
    if task is None:
        # 任务不存在（可能已被 TTL 清理），幂等返回成功
        logger.warning("回调 task_no=%s 未找到对应任务记录", task_no)
        return {"code": 10000, "message": "success"}

    # 幂等：已完成的任务不重复处理
    if task.status in (AiTaskStatus.COMPLETED.value, AiTaskStatus.FAILED.value):
        logger.info("回调 task_no=%s 任务已处理（status=%s），幂等跳过", task_no, task.status)
        return {"code": 10000, "message": "success"}

    # 处理结果
    if payload.status == "COMPLETED":
        result_data = normalize_callback_result(payload.result)
        TaskQueueService.mark_completed(db, task.id, result_data)
        logger.info("回调完成 task_no=%s task_id=%d", task_no, task.id)
    elif payload.status == "FAILED":
        TaskQueueService.mark_failed(
            db, task.id, "task_failed", payload.failed_reason or "Gateway FAILED",
        )
        logger.warning("回调失败 task_no=%s reason=%s", task_no, payload.failed_reason)
    else:
        # PENDING / PROCESSING → 忽略（任务尚未完成）
        logger.debug("回调 task_no=%s status=%s 非终态，忽略", task_no, payload.status)
        return {"code": 10000, "message": "success"}

    db.commit()
    return {"code": 10000, "message": "success"}
