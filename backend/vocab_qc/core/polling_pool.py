"""共享轮询池: 从 ai_task_queue 领取已提交的任务，统一轮询 Gateway 获取结果.

设计要点:
- 固定数量的 worker 扫描 DB，不是一个任务一个协程
- 支持 wait_for_batch 异步等待批次完成
- 全局 429 退避
- 自适应轮询间隔（poll_count 低的优先）
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from vocab_qc.core.config import settings
from vocab_qc.core.db import SyncSessionLocal
from vocab_qc.core.generators.base import (
    build_poll_body,
    parse_poll_response,
)
from vocab_qc.core.models.ai_task_queue import AiTaskQueue, AiTaskStatus
from vocab_qc.core.task_queue import TaskQueueService

logger = logging.getLogger(__name__)

# 单例
_instance: PollingPool | None = None


def _poll_interval_for_count(poll_count: int) -> float:
    """根据已轮询次数返回推荐间隔（秒）."""
    base = settings.ai_gateway_poll_interval
    if poll_count < 5:
        return base                     # 前 5 次：3s
    if poll_count < 20:
        return max(base, 5.0)           # 5-20 次：5s
    if poll_count < 50:
        return max(base, 10.0)          # 20-50 次：10s
    return max(base, 20.0)              # 50+ 次：20s


class PollingPool:
    """共享轮询池，后台 asyncio 任务持续扫描 DB 中的 submitted 任务."""

    def __init__(self) -> None:
        self._shutdown = False
        self._global_429_until: float = 0.0  # monotonic timestamp
        self._client: httpx.AsyncClient | None = None

    @classmethod
    def get_instance(cls) -> PollingPool:
        global _instance
        if _instance is None:
            _instance = cls()
        return _instance

    @classmethod
    def reset_instance(cls) -> None:
        """测试用：重置单例."""
        global _instance
        _instance = None

    def shutdown(self) -> None:
        self._shutdown = True

    async def _ensure_client(self) -> httpx.AsyncClient:
        need_new = self._client is None or self._client.is_closed
        # 检测 event loop 是否已关闭（多 worker 下可能发生）
        if not need_new:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                need_new = True
        if need_new:
            pool_size = settings.ai_poll_pool_size * 2
            self._client = httpx.AsyncClient(
                timeout=30.0,
                verify=False,
                limits=httpx.Limits(
                    max_connections=pool_size,
                    max_keepalive_connections=pool_size,
                ),
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ── 核心循环 ────────────────────────────────────────────────────

    async def run_forever(self) -> None:
        """后台运行，持续扫描并轮询任务。应在 lifespan 中作为 background task 启动.

        回调模式下作为低频安全网：仅轮询提交超过阈值的 stale 任务，扫描间隔更长。
        """
        callback_mode = settings.ai_callback_mode
        scan_interval = (
            settings.ai_poll_callback_scan_interval
            if callback_mode
            else settings.ai_poll_scan_interval
        )
        logger.info("PollingPool 启动, pool_size=%d, scan_interval=%.1fs, callback_mode=%s",
                     settings.ai_poll_pool_size, scan_interval, callback_mode)
        try:
            while not self._shutdown:
                try:
                    polled = await self._scan_and_poll(stale_only=callback_mode)
                    if polled == 0:
                        await asyncio.sleep(scan_interval)
                    else:
                        # 有任务处理了，缩短等待但不过于激进
                        await asyncio.sleep(scan_interval / 3)
                except Exception:
                    logger.exception("PollingPool scan 异常，%.0f 秒后重试", scan_interval)
                    await asyncio.sleep(scan_interval)
        finally:
            await self.close()
            logger.info("PollingPool 已停止")

    async def _scan_and_poll(self, stale_only: bool = False) -> int:
        """一轮扫描：从 DB 领取 submitted 任务，并发轮询，返回本轮处理数.

        Args:
            stale_only: True 时仅轮询提交超过 ai_poll_stale_threshold_minutes 的任务（回调模式安全网）。
        """
        # 全局 429 退避
        if time.monotonic() < self._global_429_until:
            await asyncio.sleep(self._global_429_until - time.monotonic())
            return 0

        session = SyncSessionLocal()
        try:
            from datetime import UTC, datetime, timedelta

            query = (
                session.query(AiTaskQueue)
                .filter_by(status=AiTaskStatus.SUBMITTED.value)
            )

            # 回调模式：仅轮询提交超过阈值的 stale 任务
            if stale_only:
                stale_cutoff = datetime.now(UTC) - timedelta(
                    minutes=settings.ai_poll_stale_threshold_minutes,
                )
                query = query.filter(AiTaskQueue.submitted_at < stale_cutoff)

            # 按自适应间隔过滤：只取 last_polled_at 为 NULL 或已过间隔的任务
            min_interval = settings.ai_gateway_poll_interval
            cutoff = datetime.now(UTC) - timedelta(seconds=min_interval)

            tasks = (
                query.filter(
                    (AiTaskQueue.last_polled_at.is_(None))
                    | (AiTaskQueue.last_polled_at < cutoff)
                )
                .order_by(AiTaskQueue.last_polled_at.asc().nullsfirst())
                .limit(settings.ai_poll_pool_size)
                .all()
            )
            if not tasks:
                return 0

            # 应用层精细过滤：按 poll_count 对应的自适应间隔
            now_utc = datetime.now(UTC)
            ready_tasks = []
            for t in tasks:
                if t.last_polled_at is None:
                    ready_tasks.append(t)
                else:
                    interval = _poll_interval_for_count(t.poll_count)
                    elapsed = (now_utc - t.last_polled_at).total_seconds()
                    if elapsed >= interval:
                        ready_tasks.append(t)

            if not ready_tasks:
                return 0

            # 提取需要的数据（避免在异步中访问 session）
            task_data = [
                {
                    "id": t.id,
                    "gateway_task_no": t.gateway_task_no,
                    "submit_body": t.submit_body,
                    "poll_count": t.poll_count,
                    "batch_key": t.batch_key,
                }
                for t in ready_tasks
                if t.gateway_task_no and t.submit_body
            ]
        finally:
            session.close()

        if not task_data:
            return 0

        # 并发轮询
        client = await self._ensure_client()
        poll_results = await asyncio.gather(
            *[self._poll_one(client, td) for td in task_data],
            return_exceptions=True,
        )

        # 写回结果
        session = SyncSessionLocal()
        try:
            for td, result in zip(task_data, poll_results):
                if isinstance(result, Exception):
                    log_level = logging.WARNING if td["poll_count"] > 10 else logging.DEBUG
                    logger.log(log_level, "轮询异常 task_id=%d: %s", td["id"], result)
                    TaskQueueService.increment_poll(session, td["id"])
                    continue

                status, data, error = result
                if status == "COMPLETED" and data is not None:
                    TaskQueueService.mark_completed(session, td["id"], data)
                    pass
                elif status == "FAILED":
                    TaskQueueService.mark_failed(
                        session, td["id"], "task_failed", error or "Gateway FAILED",
                    )
                    pass
                else:
                    # PENDING / PROCESSING
                    TaskQueueService.increment_poll(session, td["id"])
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        return len(task_data)

    async def _poll_one(
        self,
        client: httpx.AsyncClient,
        task_data: dict[str, Any],
    ) -> tuple[str, dict[str, Any] | None, str]:
        """对单个任务发一次 poll 请求，返回 (status, result, failed_reason)."""
        poll_url = f"{settings.ai_api_base_url}/chat/task/result"
        poll_body = build_poll_body(task_data["submit_body"], task_data["gateway_task_no"])

        response = await client.post(
            poll_url, headers={"Content-Type": "application/json"}, json=poll_body,
        )

        if response.status_code == 429:
            # 全局退避
            backoff = min(settings.ai_gateway_poll_interval * 4, 30.0)
            self._global_429_until = time.monotonic() + backoff
            logger.warning("轮询 429 限流，全局退避 %.1fs", backoff)
            return ("PENDING", None, "")

        if response.status_code >= 400:
            log_level = logging.WARNING if task_data["poll_count"] > 10 else logging.DEBUG
            logger.log(log_level, "轮询 HTTP %d, task_no=%s (poll_count=%d)",
                       response.status_code, task_data["gateway_task_no"], task_data["poll_count"])
            return ("PENDING", None, "")

        # 拦截 Gateway 业务错误码（如 502000），避免抛异常刷 WARNING
        data = response.json()
        code = data.get("code")
        if code != 10000:
            log_level = logging.WARNING if task_data["poll_count"] > 10 else logging.DEBUG
            logger.log(log_level, "轮询 Gateway code=%s, task_no=%s (poll_count=%d)",
                       code, task_data["gateway_task_no"], task_data["poll_count"])
            return ("PENDING", None, "")

        return parse_poll_response(data)

    # ── 批次等待 ────────────────────────────────────────────────────

    async def wait_for_batch(self, batch_key: str, timeout: float = 1800.0) -> bool:
        """异步等待某批次全部完成.

        回调模式（ai_callback_mode=True）：
          宽限期内仅 DB 轮询（零 HTTP），超时后降级为主动 HTTP 轮询。
        轮询模式（ai_callback_mode=False）：
          自驱动 _scan_and_poll 直到完成。

        Returns:
            True=全部完成, False=超时.
        """
        import time as _time
        deadline = _time.monotonic() + timeout
        callback_mode = settings.ai_callback_mode
        grace_deadline = _time.monotonic() + settings.ai_callback_grace_period
        degraded_logged = False

        while _time.monotonic() < deadline:
            # 检查是否已全部完成
            session = SyncSessionLocal()
            try:
                if TaskQueueService.is_batch_done(session, batch_key):
                    return True
            finally:
                session.close()

            if callback_mode and _time.monotonic() < grace_deadline:
                # 回调宽限期内：只查 DB，不主动轮询 Gateway
                await asyncio.sleep(settings.ai_poll_scan_interval)
            else:
                # 宽限期后或轮询模式：主动 HTTP 轮询
                if callback_mode and not degraded_logged:
                    logger.warning("批次 %s 回调宽限期结束，降级为主动轮询", batch_key)
                    degraded_logged = True
                try:
                    polled = await self._scan_and_poll(stale_only=callback_mode)
                except Exception:
                    logger.exception("wait_for_batch scan 异常")
                    polled = 0

                if polled == 0:
                    await asyncio.sleep(settings.ai_poll_scan_interval)
                else:
                    await asyncio.sleep(0.5)

        logger.warning("等待批次 %s 超时 (%.0fs)", batch_key, timeout)
        return False

    # ── 批量提交 ────────────────────────────────────────────────────

    async def submit_batch(self, batch_key: str) -> int:
        """将 pending 状态的任务分批提交到 Gateway.

        每批 ai_submit_batch_size 个，批次间间隔 ai_submit_stagger 秒。
        Returns:
            成功提交的任务数。
        """
        client = await self._ensure_client()
        submit_url = f"{settings.ai_api_base_url}/chat/completions"
        submitted_count = 0
        max_rounds = 1000  # 防止死循环（正常情况远低于此值）

        for _round in range(max_rounds):
            session = SyncSessionLocal()
            try:
                pending = TaskQueueService.get_pending_submit(session, batch_key)
                if not pending:
                    break

                batch = pending[:settings.ai_submit_batch_size]
                batch_data = [
                    {"id": t.id, "submit_body": t.submit_body}
                    for t in batch
                ]
            finally:
                session.close()

            # 并发提交本批
            results = await asyncio.gather(
                *[self._submit_one(client, submit_url, td) for td in batch_data],
                return_exceptions=True,
            )

            # 写回结果——逐个 commit，确保回调到达时 gateway_task_no 已持久化
            session = SyncSessionLocal()
            try:
                all_failed = True
                for td, result in zip(batch_data, results):
                    if isinstance(result, Exception):
                        logger.warning("提交失败 task_id=%d: %s", td["id"], result)
                        TaskQueueService.mark_failed(
                            session, td["id"], "submit_failed", str(result),
                        )
                    else:
                        TaskQueueService.mark_submitted(session, td["id"], result)
                        submitted_count += 1
                        all_failed = False
                    session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

            # 如果整批全部失败，直接退出防止无限重试
            if all_failed:
                logger.error("批次 %s 本轮全部提交失败，终止提交", batch_key)
                break

            # 批次间 stagger
            if settings.ai_submit_stagger > 0:
                await asyncio.sleep(settings.ai_submit_stagger)

        logger.info("批次 %s 提交完成, 共 %d 个任务", batch_key, submitted_count)
        return submitted_count

    async def _submit_one(
        self,
        client: httpx.AsyncClient,
        url: str,
        task_data: dict[str, Any],
    ) -> str:
        """提交单个任务到 Gateway，返回 task_no。失败时重试 1 次（重建 client）."""
        from vocab_qc.core.generators.base import parse_async_submit_response

        for attempt in range(2):
            try:
                response = await client.post(
                    url, headers={"Content-Type": "application/json"}, json=task_data["submit_body"],
                )
                if response.status_code == 429:
                    raise RuntimeError(f"Gateway 429 限流, task_id={task_data['id']}")
                if response.status_code >= 400:
                    raise RuntimeError(f"Gateway HTTP {response.status_code}: {response.text[:200]}")

                return parse_async_submit_response(response.json())
            except Exception:
                if attempt == 0:
                    logger.warning("提交重试 task_id=%d (attempt %d)", task_data["id"], attempt + 1)
                    client = await self._ensure_client()
                    continue
                raise
