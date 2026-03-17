"""Prompt 管理服务."""

import hashlib
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from vocab_qc.core.models.prompt import Prompt

logger = logging.getLogger(__name__)

# 文件名 → (dimension, 显示名)
_PROMPT_FILE_MAP: list[tuple[str, str, str]] = [
    ("语块.md", "chunk", "语块"),
    ("例句.md", "sentence", "例句"),
    ("音节.md", "syllable", "音节"),
    ("助记-词根词缀.md", "mnemonic_root_affix", "助记-词根词缀"),
    ("助记-词中词.md", "mnemonic_word_in_word", "助记-词中词"),
    ("助记-音义联想.md", "mnemonic_sound_meaning", "助记-音义联想"),
    ("助记-考试应用.md", "mnemonic_exam_app", "助记-考试应用"),
]

# 维度→模型映射（例句用 GPT，其余用 Gemini）
_DIMENSION_MODEL_MAP: dict[str, str] = {
    "chunk": "gemini-3-flash-preview|efficiency",
    "sentence": "gpt-5.2|efficiency",
    "syllable": "gemini-3-flash-preview|efficiency",
    "mnemonic_root_affix": "gemini-3-flash-preview|efficiency",
    "mnemonic_word_in_word": "gemini-3-flash-preview|efficiency",
    "mnemonic_sound_meaning": "gemini-3-flash-preview|efficiency",
    "mnemonic_exam_app": "gemini-3-flash-preview|efficiency",
}
DEFAULT_MODEL = "gemini-3-flash-preview|efficiency"


def _model_for_dimension(dimension: str) -> str:
    """根据维度返回对应的模型名。"""
    return _DIMENSION_MODEL_MAP.get(dimension, DEFAULT_MODEL)


def _compute_file_hash(content: str) -> str:
    """计算内容 SHA-256 哈希。"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _find_prompts_dir() -> Path | None:
    """查找 docs/prompts 目录。"""
    # 从当前文件向上查找项目根目录
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "docs" / "prompts"
        if candidate.is_dir():
            return candidate
    return None


def seed_defaults(session: Session) -> int:
    """从 docs/prompts/ 目录读取 Prompt 模板并插入（仅在表为空时）."""
    count = session.query(Prompt).count()
    if count > 0:
        return 0

    prompts_dir = _find_prompts_dir()
    if prompts_dir is None:
        return 0

    created = 0
    for category, subdir in [("generation", "generation"), ("qa", "quality")]:
        category_dir = prompts_dir / subdir
        if not category_dir.is_dir():
            continue
        for filename, dimension, display_name in _PROMPT_FILE_MAP:
            filepath = category_dir / filename
            if not filepath.exists():
                continue
            content = filepath.read_text(encoding="utf-8").strip()
            session.add(Prompt(
                name=f"{display_name}{'生成' if category == 'generation' else '质检'}",
                category=category,
                dimension=dimension,
                model=_model_for_dimension(dimension),
                content=content,
                source="file",
                file_hash=_compute_file_hash(content),
            ))
            created += 1

    session.flush()
    return created


def list_prompts(
    session: Session,
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> list[Prompt]:
    """获取 Prompt 列表."""
    q = session.query(Prompt)
    if category:
        q = q.filter_by(category=category)
    if is_active is not None:
        q = q.filter_by(is_active=is_active)
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
        model=data.get("model", _model_for_dimension(data["dimension"])),
        content=data.get("content", ""),
        ai_api_base_url=data.get("ai_api_base_url"),
        created_by=user_id,
    )
    session.add(prompt)
    session.flush()
    return prompt


def update_prompt(session: Session, prompt_id: int, data: dict) -> Optional[Prompt]:
    prompt = session.query(Prompt).filter_by(id=prompt_id).first()
    if prompt is None:
        return None
    for field in ("name", "model", "content", "is_active", "ai_api_base_url"):
        if field in data:
            setattr(prompt, field, data[field])
    # PM-H3: 用户手动编辑 content 后标记 source="manual"
    if "content" in data:
        prompt.source = "manual"
    session.flush()
    return prompt


def archive_prompt(session: Session, prompt_id: int) -> Optional[Prompt]:
    """归档 Prompt（软删除）."""
    prompt = session.query(Prompt).filter_by(id=prompt_id).first()
    if prompt is None:
        return None
    prompt.is_active = False
    session.flush()
    return prompt


def restore_prompt(session: Session, prompt_id: int) -> Optional[Prompt]:
    """复原已归档的 Prompt."""
    prompt = session.query(Prompt).filter_by(id=prompt_id).first()
    if prompt is None:
        return None
    prompt.is_active = True
    session.flush()
    return prompt


def delete_prompt(session: Session, prompt_id: int) -> bool:
    """永久删除 Prompt（保留兼容性）."""
    prompt = session.query(Prompt).filter_by(id=prompt_id).first()
    if prompt is None:
        return False
    session.delete(prompt)
    session.flush()
    return True


def sync_prompts(session: Session, dry_run: bool = False) -> dict:
    """PM-H3: 同步 docs/prompts/ 文件到 DB。

    - DB 无记录 → 新建 (source="file")
    - DB 有 + source="file" + hash 不同 → 更新 content + file_hash
    - DB 有 + source="manual" → 跳过（用户手动编辑的不覆盖）
    """
    prompts_dir = _find_prompts_dir()
    if prompts_dir is None:
        return {"created": 0, "updated": 0, "skipped": 0}

    created = 0
    updated = 0
    skipped = 0

    category_map = [("generation", "generation"), ("qa", "quality")]

    for category, subdir in category_map:
        category_dir = prompts_dir / subdir
        if not category_dir.is_dir():
            continue
        for filename, dimension, display_name in _PROMPT_FILE_MAP:
            filepath = category_dir / filename
            if not filepath.exists():
                continue

            content = filepath.read_text(encoding="utf-8").strip()
            file_hash = _compute_file_hash(content)

            existing = (
                session.query(Prompt)
                .filter_by(category=category, dimension=dimension, is_active=True)
                .first()
            )

            if existing is None:
                if not dry_run:
                    session.add(Prompt(
                        name=f"{display_name}{'生成' if category == 'generation' else '质检'}",
                        category=category,
                        dimension=dimension,
                        model=_model_for_dimension(dimension),
                        content=content,
                        source="file",
                        file_hash=file_hash,
                    ))
                created += 1
            elif existing.source == "manual":
                skipped += 1
            elif existing.file_hash != file_hash:
                if not dry_run:
                    existing.content = content
                    existing.file_hash = file_hash
                    existing.model = _model_for_dimension(dimension)
                updated += 1
            else:
                skipped += 1

    if not dry_run:
        session.flush()

    return {"created": created, "updated": updated, "skipped": skipped}
