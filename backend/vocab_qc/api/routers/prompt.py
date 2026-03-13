"""Prompt 管理 API 路由."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from vocab_qc.api.deps import get_current_user, get_db, require_role
from vocab_qc.api.schemas.prompt import PromptCreateRequest, PromptResponse, PromptUpdateRequest
from vocab_qc.core.models.user import User
from vocab_qc.core.services import prompt_service

router = APIRouter(prefix="/api/prompts", tags=["Prompt"])


@router.get("", response_model=list[PromptResponse])
def list_prompts(
    category: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """获取 Prompt 列表（仅管理员）."""
    return prompt_service.list_prompts(db, category=category, is_active=is_active)


@router.get("/sync/preview")
def sync_preview(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """预览 Prompt 同步结果（dry run）。"""
    return prompt_service.sync_prompts(db, dry_run=True)


@router.post("/sync")
def sync_prompts(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """同步 docs/prompts/ 文件到 DB。"""
    result = prompt_service.sync_prompts(db)
    db.commit()
    return result


@router.get("/{prompt_id}", response_model=PromptResponse)
def get_prompt(
    prompt_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """获取单个 Prompt（仅管理员）."""
    prompt = prompt_service.get_prompt(db, prompt_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt 不存在")
    return prompt


@router.post("", response_model=PromptResponse, status_code=201)
def create_prompt(
    req: PromptCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """创建 Prompt."""
    result = prompt_service.create_prompt(db, req.model_dump(), user_id=current_user.id)
    db.commit()
    return result


@router.put("/{prompt_id}", response_model=PromptResponse)
def update_prompt(
    prompt_id: int,
    req: PromptUpdateRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """更新 Prompt."""
    prompt = prompt_service.update_prompt(db, prompt_id, req.model_dump(exclude_unset=True))
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt 不存在")
    db.commit()
    return prompt


@router.delete("/{prompt_id}")
def archive_prompt(
    prompt_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """归档 Prompt（软删除）."""
    prompt = prompt_service.archive_prompt(db, prompt_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt 不存在")
    db.commit()
    return {"message": "已归档"}


@router.post("/{prompt_id}/restore", response_model=PromptResponse)
def restore_prompt(
    prompt_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """复原已归档的 Prompt."""
    prompt = prompt_service.restore_prompt(db, prompt_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt 不存在")
    db.commit()
    return prompt


@router.post("/seed")
def seed_prompts(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_role("admin")),
):
    """初始化默认 Prompt."""
    count = prompt_service.seed_defaults(db)
    db.commit()
    return {"seeded": count}
