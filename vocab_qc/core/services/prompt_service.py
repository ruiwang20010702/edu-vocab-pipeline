"""Prompt 管理服务."""

from typing import Optional

from sqlalchemy.orm import Session

from vocab_qc.core.models.prompt import Prompt

# 默认 Prompt 种子数据
DEFAULT_PROMPTS = [
    {
        "name": "语块生成",
        "category": "generation",
        "dimension": "chunk",
        "model": "gpt-4o-mini",
        "content": "请为单词 {word} 的义项「{pos} {definition}」生成一个常用语块...",
    },
    {
        "name": "例句生成",
        "category": "generation",
        "dimension": "sentence",
        "model": "gpt-4o-mini",
        "content": "请为单词 {word} 的义项「{pos} {definition}」生成一个例句...",
    },
    {
        "name": "助记生成",
        "category": "generation",
        "dimension": "mnemonic",
        "model": "gpt-4o-mini",
        "content": "请为单词 {word} 生成助记法...",
    },
    {
        "name": "语块质检",
        "category": "qa",
        "dimension": "chunk",
        "model": "gpt-4o-mini",
        "content": "请检查以下语块是否符合标准...",
    },
    {
        "name": "例句质检",
        "category": "qa",
        "dimension": "sentence",
        "model": "gpt-4o-mini",
        "content": "请检查以下例句是否符合标准...",
    },
]


def seed_defaults(session: Session) -> int:
    """插入默认 Prompt（仅在表为空时）."""
    count = session.query(Prompt).count()
    if count > 0:
        return 0
    for data in DEFAULT_PROMPTS:
        session.add(Prompt(**data))
    session.flush()
    return len(DEFAULT_PROMPTS)


def list_prompts(
    session: Session,
    category: Optional[str] = None,
) -> list[Prompt]:
    """获取 Prompt 列表."""
    q = session.query(Prompt)
    if category:
        q = q.filter_by(category=category)
    return q.order_by(Prompt.id).all()


def get_prompt(session: Session, prompt_id: int) -> Optional[Prompt]:
    return session.query(Prompt).filter_by(id=prompt_id).first()


def get_active_prompt(session: Session, category: str, dimension: str) -> Optional[Prompt]:
    """获取指定维度的活跃 Prompt."""
    return (
        session.query(Prompt)
        .filter_by(category=category, dimension=dimension, is_active=True)
        .order_by(Prompt.updated_at.desc().nullslast(), Prompt.id.desc())
        .first()
    )


def create_prompt(session: Session, data: dict, user_id: Optional[int] = None) -> Prompt:
    prompt = Prompt(
        name=data["name"],
        category=data["category"],
        dimension=data["dimension"],
        model=data.get("model", "gpt-4o-mini"),
        content=data.get("content", ""),
        created_by=user_id,
    )
    session.add(prompt)
    session.flush()
    return prompt


def update_prompt(session: Session, prompt_id: int, data: dict) -> Optional[Prompt]:
    prompt = session.query(Prompt).filter_by(id=prompt_id).first()
    if prompt is None:
        return None
    for field in ("name", "model", "content", "is_active"):
        if field in data:
            setattr(prompt, field, data[field])
    session.flush()
    return prompt


def delete_prompt(session: Session, prompt_id: int) -> bool:
    prompt = session.query(Prompt).filter_by(id=prompt_id).first()
    if prompt is None:
        return False
    session.delete(prompt)
    session.flush()
    return True
