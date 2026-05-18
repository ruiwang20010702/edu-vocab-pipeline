"""批次相关 Pydantic 模型."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

from vocab_qc.core.models.enums import REGENERATABLE_DIMENSIONS


class BatchResponse(BaseModel):
    id: int
    user_id: int
    status: str
    word_count: int
    reviewed_count: int
    created_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class BatchWordItem(BaseModel):
    review_id: int
    content_item_id: int
    dimension: str
    reason: str
    status: str
    resolution: Optional[str]


class BatchWordResponse(BaseModel):
    word_id: int
    items: list[BatchWordItem]


class BatchDetailResponse(BaseModel):
    batch: BatchResponse
    words: list[BatchWordResponse]


class ReviewerStat(BaseModel):
    user_id: int
    batch_count: int
    reviewed_words: int


class BatchStatsResponse(BaseModel):
    pending_words: int
    reviewed_words: int
    reviewers: list[ReviewerStat]


class ProduceResponse(BaseModel):
    batch_id: int
    status: str


class ProduceRequest(BaseModel):
    """生产/重新生产请求体。

    - dimensions=None ⇒ 维持旧行为（只生成 PENDING ContentItem）
    - dimensions=[...] ⇒ 先 reset 指定维度（已通过/失败的都覆盖），再触发生产
    - force_overwrite_recent=True ⇒ 不跳过"已用最新 prompt 生成"的 ContentItem
      （默认 False：generated_with_prompt_id + hash 与当前 active prompt 双维匹配
       的会自动跳过，防跨包重复劳动。字段名沿用历史命名，语义已升级为按 prompt
       版本判断而非按时间窗）
    """

    dimensions: Optional[list[str]] = None
    force_overwrite_recent: bool = False

    @field_validator("dimensions")
    @classmethod
    def _validate_dimensions(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        if len(v) == 0:
            raise ValueError("dimensions 不能为空列表；如需全量生产请省略此字段或传 null")
        bad = set(v) - REGENERATABLE_DIMENSIONS
        if bad:
            raise ValueError(f"非法维度: {sorted(bad)}；合法值: {sorted(REGENERATABLE_DIMENSIONS)}")
        # 去重保留首次出现顺序
        seen: set[str] = set()
        return [d for d in v if not (d in seen or seen.add(d))]


class ProducePreviewResponse(BaseModel):
    """dry-run 预览受影响项数量，供前端二次确认 UI 使用。

    跨包去重：would_reset 是实际会动的数量；skipped_recently 是因
    24h 时间窗被自动跳过的数量（已被其他包重生过的共享 ContentItem）。
    """

    content_items: int          # 总匹配数（含跳过）
    would_reset: int            # 真正会动的数量
    skipped_recently: int       # 因时间窗被跳过
    review_items: int           # 真正要删的 review_items 数
    distinct_words: int
    by_dimension: dict[str, int]
