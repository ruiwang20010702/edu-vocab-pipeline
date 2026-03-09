"""审计日志服务."""

from typing import Any, Optional

from sqlalchemy.orm import Session

from vocab_qc.core.models import AuditLogV2


def log_action(
    session: Session,
    entity_type: str,
    entity_id: int,
    action: str,
    actor: str,
    old_value: Optional[dict[str, Any]] = None,
    new_value: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> AuditLogV2:
    entry = AuditLogV2(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor=actor,
        old_value=old_value,
        new_value=new_value,
        metadata_=metadata,
    )
    session.add(entry)
    session.flush()
    return entry
