"""AI Gateway 回调端点: 接收异步任务完成通知."""

import json
import logging
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_db, require_role
from vocab_qc.api.schemas.callback import AiTaskCallbackPayload
from vocab_qc.core.config import settings
from vocab_qc.core.models.ai_task_queue import AiTaskQueue, AiTaskStatus
from vocab_qc.core.models.user import User
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

    # 调试日志：记录来源 IP + 回调数据
    client_ip = request.client.host if request.client else "unknown"
    logger.info(
        "回调详情 ip=%s task_no=%s status=%s result_type=%s result_preview=%s",
        client_ip, payload.task_no, payload.status,
        type(payload.result).__name__,
        str(payload.result)[:500] if payload.result else "None",
    )

    task_no = payload.task_no

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


@router.post("/test-gateway")
def test_gateway_callback(
    _current_user: User = Depends(require_role("admin")),
) -> dict:
    """向 Gateway 提交一次简单测试任务，验证回调链路是否通畅。

    仅提交，不等待结果——回调到达时会出现在服务器日志中。
    """
    if not settings.ai_gateway_mode:
        raise HTTPException(status_code=400, detail="未启用 AI Gateway 模式")
    if not settings.ai_callback_mode or not settings.ai_callback_url:
        raise HTTPException(status_code=400, detail="未配置回调地址 (AI_CALLBACK_URL)")

    from vocab_qc.core.generators.base import ContentGenerator

    body = {
        "model": settings.ai_model,
        "provider": ContentGenerator._resolve_gateway_provider(settings.ai_model),
        "api_key": settings.ai_api_key,
        "biz_type": settings.ai_gateway_biz_type,
        "biz_id": str(uuid.uuid4()),
        "stream": False,
        "async": True,
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": "Reply with: {\"status\": \"ok\"}"}]},
            {"role": "user", "content": [{"type": "text", "text": "ping"}]},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "client_callback_url": settings.ai_callback_url,
    }

    submit_url = f"{settings.ai_api_base_url}/chat/completions"

    try:
        with httpx.Client(timeout=15.0, verify=False) as client:
            resp = client.post(submit_url, json=body, headers={"Content-Type": "application/json"})
            data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gateway 请求失败: {e}")

    if data.get("code") != 10000:
        raise HTTPException(status_code=502, detail=f"Gateway 返回异常: {data}")

    task_no = data.get("res", "")
    logger.info("Gateway 测试任务已提交 task_no=%s callback_url=%s", task_no, settings.ai_callback_url)

    return {
        "task_no": task_no,
        "callback_url": settings.ai_callback_url,
        "message": "已提交测试任务，请在服务器日志中查看回调结果（搜索 '回调详情'）",
    }
