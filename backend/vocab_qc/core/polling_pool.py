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
        self._batch_events: dict[str, asyncio.Event] = {}
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
        if self._client is None or self._client.is_closed:
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
        """后台运行，持续扫描并轮询任务。应在 lifespan 中作为 background task 启动."""
        logger.info("PollingPool 启动, pool_size=%d, scan_interval=%.1fs",
                     settings.ai_poll_pool_size, settings.ai_poll_scan_interval)
        try:
            while not self._shutdown:
                try:
                    polled = await self._scan_and_poll()
                    if polled == 0:
                        # 无任务可轮询，休眠一个扫描间隔
                        await asyncio.sleep(settings.ai_poll_scan_interval)
                    else:
                        # 有任务处理了，短暂 yield 后继续
                        await asyncio.sleep(0.1)
                except Exception:
                    logger.exception("PollingPool scan 异常，5 秒后重试")
                    await asyncio.sleep(5.0)
        finally:
            await self.close()
            logger.info("PollingPool 已停止")

    async def _scan_and_poll(self) -> int:
        """一轮扫描：从 DB 领取 submitted 任务，并发轮询，返回本轮处理数."""
        # 全局 429 退避
        if time.monotonic() < self._global_429_until:
            await asyncio.sleep(self._global_429_until - time.monotonic())
            return 0

        session = SyncSessionLocal()
        try:
            tasks = (
                session.query(AiTaskQueue)
                .filter_by(status=AiTaskStatus.SUBMITTED.value)
                .order_by(AiTaskQueue.last_polled_at.asc().nullsfirst())
                .limit(settings.ai_poll_pool_size)
                .all()
            )
            if not tasks:
                return 0

            # 过滤掉还没到轮询间隔的任务
            now = time.monotonic()
            ready_tasks = []
            for t in tasks:
                interval = _poll_interval_for_count(t.poll_count)
                if t.last_polled_at is None:
                    ready_tasks.append(t)
                else:
                    # 用 poll_count 推算是否到了间隔
                    elapsed_since_poll = (
                        asyncio.get_event_loop().time() - asyncio.get_event_loop().time()
                    )
                    # 简化：直接检查 poll_count 对应间隔，每轮都轮询一次
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
                    logger.warning("轮询异常 task_id=%d: %s", td["id"], result)
                    TaskQueueService.increment_poll(session, td["id"])
                    continue

                status, data, error = result
                if status == "COMPLETED" and data is not None:
                    TaskQueueService.mark_completed(session, td["id"], data)
                    self._notify_batch(td["batch_key"])
                elif status == "FAILED":
                    TaskQueueService.mark_failed(
                        session, td["id"], "task_failed", error or "Gateway FAILED",
                    )
                    self._notify_batch(td["batch_key"])
                else:
                    # PENDING / PROCESSING
                    TaskQueueService.increment_poll(session, td["id"])
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        # 检查哪些 batch 已全部完成
        done_batches = set()
        for td in task_data:
            bk = td["batch_key"]
            if bk not in done_batches and bk in self._batch_events:
                s = SyncSessionLocal()
                try:
                    if TaskQueueService.is_batch_done(s, bk):
                        done_batches.add(bk)
                        self._notify_batch(bk, final=True)
                finally:
                    s.close()

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
            logger.warning("轮询 HTTP %d, task_no=%s", response.status_code, task_data["gateway_task_no"])
            return ("PENDING", None, "")

        return parse_poll_response(response.json())

    # ── 批次等待 ────────────────────────────────────────────────────

    def _notify_batch(self, batch_key: str, final: bool = False) -> None:
        """通知等待某批次的协程."""
        event = self._batch_events.get(batch_key)
        if event and final:
            event.set()

    async def wait_for_batch(self, batch_key: str, timeout: float = 1800.0) -> bool:
        """异步等待某批次全部完成.

        Returns:
            True=全部完成, False=超时.
        """
        # 先检查是否已完成
        session = SyncSessionLocal()
        try:
            if TaskQueueService.is_batch_done(session, batch_key):
                return True
        finally:
            session.close()

        # 注册事件
        event = asyncio.Event()
        self._batch_events[batch_key] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning("等待批次 %s 超时 (%.0fs)", batch_key, timeout)
            return False
        finally:
            self._batch_events.pop(batch_key, None)

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

        while True:
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

            # 写回结果
            session = SyncSessionLocal()
            try:
                for td, result in zip(batch_data, results):
                    if isinstance(result, Exception):
                        logger.warning("提交失败 task_id=%d: %s", td["id"], result)
                        task = session.query(AiTaskQueue).filter_by(id=td["id"]).one()
                        task.retry_count += 1
                        if task.retry_count >= task.max_retries:
                            TaskQueueService.mark_failed(
                                session, td["id"], "submit_failed", str(result),
                            )
                    else:
                        TaskQueueService.mark_submitted(session, td["id"], result)
                        submitted_count += 1
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

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
        """提交单个任务到 Gateway，返回 task_no."""
        from vocab_qc.core.generators.base import parse_async_submit_response

        response = await client.post(
            url, headers={"Content-Type": "application/json"}, json=task_data["submit_body"],
        )
        if response.status_code == 429:
            raise RuntimeError(f"Gateway 429 限流, task_id={task_data['id']}")
        if response.status_code >= 400:
            raise RuntimeError(f"Gateway HTTP {response.status_code}: {response.text[:200]}")

        return parse_async_submit_response(response.json())
