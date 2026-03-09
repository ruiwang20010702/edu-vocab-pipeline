"""审计日志服务."""

from typing import Any, Optional

from sqlalchemy.orm import Session

from vocab_qc.core.models import AuditLogV2


def _truncate_audit_values(values: dict | None, max_len: int = 200) -> dict | None:
    """截断审计日志中过长的内容字段，避免日志膨胀."""
    if not values:
        return values
    result = dict(values)
    for key in ("content", "content_cn"):
        if key in result and isinstance(result[key], str) and len(result[key]) > max_len:
            result[key] = result[key][:max_len] + "...(truncated)"
    return result


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
        old_value=_truncate_audit_values(old_value),
        new_value=_truncate_audit_values(new_value),
        metadata_=metadata,
    )
    session.add(entry)
    session.flush()
    return entry
