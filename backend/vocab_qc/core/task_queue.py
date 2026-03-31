"""AI 任务队列服务: 管理 Gateway 异步任务的入队、提交记录、结果收集和重启恢复."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Optional

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from vocab_qc.core.models.ai_task_queue import AiTaskQueue, AiTaskStatus

logger = logging.getLogger(__name__)

# 超过此时长未更新的 submitted/polling 任务视为 stale，需恢复
STALE_THRESHOLD_MINUTES = 30

# 已完成任务保留天数，超过后可清理
TTL_DAYS = 7


@dataclass(frozen=True)
class TaskSpec:
    """入队任务规格，包含构造 Gateway 请求所需的全部信息."""

    batch_key: str
    phase: str                              # "generation" / "qc_layer2"
    submit_body: dict                       # Gateway 请求 body（含 model/provider/api_key/messages 等）
    content_item_id: int | None = None
    dimension: str | None = None
    ai_model: str | None = None
    word_id: int | None = None
    package_id: int | None = None
    max_retries: int = 3


class TaskQueueService:
    """AI 任务队列的增删改查操作."""

    @staticmethod
    def enqueue_tasks(session: Session, specs: list[TaskSpec]) -> list[int]:
        """批量入队，返回新建的任务 ID 列表."""
        tasks = [
            AiTaskQueue(
                batch_key=spec.batch_key,
                content_item_id=spec.content_item_id,
                phase=spec.phase,
                dimension=spec.dimension,
                submit_body=spec.submit_body,
                status=AiTaskStatus.PENDING.value,
                ai_model=spec.ai_model,
                word_id=spec.word_id,
                package_id=spec.package_id,
                max_retries=spec.max_retries,
            )
            for spec in specs
        ]
        session.add_all(tasks)
        session.flush()
        ids = [t.id for t in tasks]
        logger.info("入队 %d 个任务, batch_key=%s", len(ids), specs[0].batch_key if specs else "?")
        return ids

    @staticmethod
    def mark_submitted(
        session: Session,
        task_id: int,
        gateway_task_no: str,
    ) -> None:
        """提交成功后记录 task_no."""
        task = session.query(AiTaskQueue).filter_by(id=task_id).one()
        task.status = AiTaskStatus.SUBMITTED.value
        task.gateway_task_no = gateway_task_no
        task.submitted_at = datetime.now(UTC)
        session.flush()

    @staticmethod
    def mark_completed(
        session: Session,
        task_id: int,
        result_data: dict,
    ) -> None:
        """轮询完成，写入结果."""
        task = session.query(AiTaskQueue).filter_by(id=task_id).one()
        task.status = AiTaskStatus.COMPLETED.value
        task.result_data = result_data
        task.completed_at = datetime.now(UTC)
        session.flush()

    @staticmethod
    def mark_failed(
        session: Session,
        task_id: int,
        error_type: str,
        error_message: str,
    ) -> None:
        """标记失败."""
        task = session.query(AiTaskQueue).filter_by(id=task_id).one()
        task.status = AiTaskStatus.FAILED.value
        task.error_type = error_type
        task.error_message = error_message
        task.completed_at = datetime.now(UTC)
        session.flush()

    @staticmethod
    def increment_poll(session: Session, task_id: int) -> None:
        """更新轮询计数和时间（任务仍在 Gateway 处理中）."""
        task = session.query(AiTaskQueue).filter_by(id=task_id).one()
        task.poll_count += 1
        task.last_polled_at = datetime.now(UTC)
        session.flush()

    @staticmethod
    def collect_completed(session: Session, batch_key: str) -> list[AiTaskQueue]:
        """收集某批次所有已完成（含失败）的任务."""
        return (
            session.query(AiTaskQueue)
            .filter_by(batch_key=batch_key)
            .filter(AiTaskQueue.status.in_([
                AiTaskStatus.COMPLETED.value,
                AiTaskStatus.FAILED.value,
            ]))
            .all()
        )

    @staticmethod
    def get_pending_submit(session: Session, batch_key: str) -> list[AiTaskQueue]:
        """获取待提交的任务."""
        return (
            session.query(AiTaskQueue)
            .filter_by(batch_key=batch_key, status=AiTaskStatus.PENDING.value)
            .order_by(AiTaskQueue.id)
            .all()
        )

    @staticmethod
    def get_submitted_for_poll(
        session: Session,
        batch_key: Optional[str] = None,
        limit: int = 100,
    ) -> list[AiTaskQueue]:
        """获取待轮询的任务，按 last_polled_at 升序（优先轮询最久未查的）."""
        q = session.query(AiTaskQueue).filter_by(status=AiTaskStatus.SUBMITTED.value)
        if batch_key:
            q = q.filter_by(batch_key=batch_key)
        return (
            q.order_by(AiTaskQueue.last_polled_at.asc().nullsfirst())
            .limit(limit)
            .all()
        )

    @staticmethod
    def is_batch_done(session: Session, batch_key: str) -> bool:
        """检查批次是否全部完成（无 pending/submitted/polling 状态）.

        若批次不存在（无任何记录），返回 False 而非误判完成。
        """
        total = session.query(AiTaskQueue).filter_by(batch_key=batch_key).count()
        if total == 0:
            return False  # 批次不存在，不算完成

        active_count = (
            session.query(AiTaskQueue)
            .filter_by(batch_key=batch_key)
            .filter(AiTaskQueue.status.in_([
                AiTaskStatus.PENDING.value,
                AiTaskStatus.SUBMITTED.value,
                AiTaskStatus.POLLING.value,
            ]))
            .count()
        )
        return active_count == 0

    @staticmethod
    def batch_progress(session: Session, batch_key: str) -> dict[str, int]:
        """返回批次进度统计."""
        tasks = session.query(AiTaskQueue).filter_by(batch_key=batch_key).all()
        stats: dict[str, int] = {"total": len(tasks)}
        for status in AiTaskStatus:
            stats[status.value] = sum(1 for t in tasks if t.status == status.value)
        return stats

    @staticmethod
    def recover_interrupted(session: Session) -> int:
        """重启恢复：将 stale 的 submitted/polling 任务重置为 submitted 以便重新轮询.

        Returns:
            恢复的任务数量。
        """
        stale_cutoff = datetime.now(UTC) - timedelta(minutes=STALE_THRESHOLD_MINUTES)
        count = session.execute(
            update(AiTaskQueue)
            .where(
                AiTaskQueue.status.in_([
                    AiTaskStatus.SUBMITTED.value,
                    AiTaskStatus.POLLING.value,
                ]),
                AiTaskQueue.last_polled_at < stale_cutoff,
            )
            .values(status=AiTaskStatus.SUBMITTED.value)
        ).rowcount

        # 也恢复从未被轮询过的 submitted 任务（last_polled_at IS NULL，但 submitted_at 已过期）
        count_null = session.execute(
            update(AiTaskQueue)
            .where(
                AiTaskQueue.status.in_([
                    AiTaskStatus.SUBMITTED.value,
                    AiTaskStatus.POLLING.value,
                ]),
                AiTaskQueue.last_polled_at.is_(None),
                AiTaskQueue.submitted_at < stale_cutoff,
            )
            .values(status=AiTaskStatus.SUBMITTED.value)
        ).rowcount

        total = count + count_null
        if total:
            logger.warning("恢复 %d 个中断的 AI 任务", total)
        return total

    @staticmethod
    def cancel_batch(session: Session, batch_key: str) -> int:
        """取消批次中所有未完成的任务."""
        count = session.execute(
            update(AiTaskQueue)
            .where(
                AiTaskQueue.batch_key == batch_key,
                AiTaskQueue.status.in_([
                    AiTaskStatus.PENDING.value,
                    AiTaskStatus.SUBMITTED.value,
                    AiTaskStatus.POLLING.value,
                ]),
            )
            .values(status=AiTaskStatus.CANCELLED.value)
        ).rowcount
        if count:
            logger.info("取消批次 %s 中 %d 个任务", batch_key, count)
        return count

    @staticmethod
    def fail_expired_tasks(session: Session, max_age_hours: int = 2) -> int:
        """将提交超过 max_age_hours 仍 SUBMITTED 的任务标记为 FAILED.

        用于清理 Gateway 已丢失或回调遗漏的僵尸任务。
        """
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
        count = session.execute(
            update(AiTaskQueue)
            .where(
                AiTaskQueue.status == AiTaskStatus.SUBMITTED.value,
                AiTaskQueue.submitted_at < cutoff,
            )
            .values(
                status=AiTaskStatus.FAILED.value,
                error_type="expired",
                error_message=f"提交超过 {max_age_hours}h 仍未完成，标记为超时失败",
                completed_at=datetime.now(UTC),
            )
        ).rowcount
        if count:
            logger.warning("标记 %d 个超时任务为失败 (超过 %dh)", count, max_age_hours)
        return count

    @staticmethod
    def cleanup_old(session: Session, days: int = TTL_DAYS) -> int:
        """清理已完成/失败/取消超过 N 天的任务记录.

        Returns:
            删除的记录数。
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)
        count = session.execute(
            delete(AiTaskQueue).where(
                AiTaskQueue.status.in_([
                    AiTaskStatus.COMPLETED.value,
                    AiTaskStatus.FAILED.value,
                    AiTaskStatus.CANCELLED.value,
                ]),
                AiTaskQueue.completed_at < cutoff,
            )
        ).rowcount
        if count:
            logger.info("清理 %d 条超过 %d 天的任务记录", count, days)
        return count
