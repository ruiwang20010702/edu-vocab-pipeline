"""内容生成服务."""

from typing import Optional

from sqlalchemy.orm import Session

from vocab_qc.core.models import ContentItem
from vocab_qc.core.services.audit_service import log_action


class GenerationService:
    """内容生成服务: 协调生成器，处理重新生成逻辑."""

    def regenerate_dimension(
        self,
        session: Session,
        content_item: ContentItem,
        new_content: str,
        new_content_cn: Optional[str] = None,
        actor: str = "system",
    ) -> ContentItem:
        """重新生成某个维度的内容（供 review_service 调用）."""
        old_content = content_item.content
        content_item.content = new_content
        if new_content_cn is not None:
            content_item.content_cn = new_content_cn

        log_action(
            session,
            entity_type="content_item",
            entity_id=content_item.id,
            action="regenerate",
            actor=actor,
            old_value={"content": old_content},
            new_value={"content": new_content},
        )

        session.flush()
        return content_item
