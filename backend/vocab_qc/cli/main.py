"""CLI 入口."""

import typer

from vocab_qc.cli.qc_commands import qc_app
from vocab_qc.cli.review_commands import review_app

app = typer.Typer(name="vocab", help="英语词汇学习系统 V2.0 质检工具")
app.add_typer(qc_app, name="qc")
app.add_typer(review_app, name="review")


@app.callback()
def main():
    """词汇质检 CLI."""


@app.command()
def cleanup_orphan_mnemonics(dry_run: bool = typer.Option(True, help="仅预览，不删除")):
    """清理 meaning_id=NULL 的旧助记 ContentItem。"""
    from vocab_qc.core.db import SyncSessionLocal
    from vocab_qc.core.models.content_layer import ContentItem
    from vocab_qc.core.models.enums import MNEMONIC_DIMENSIONS

    session = SyncSessionLocal()
    try:
        orphans = (
            session.query(ContentItem)
            .filter(
                ContentItem.dimension.in_(MNEMONIC_DIMENSIONS),
                ContentItem.meaning_id.is_(None),
            )
            .all()
        )
        typer.echo(f"发现 {len(orphans)} 条 meaning_id=NULL 的旧助记")
        if orphans and not dry_run:
            session.query(ContentItem).filter(
                ContentItem.dimension.in_(MNEMONIC_DIMENSIONS),
                ContentItem.meaning_id.is_(None),
            ).delete(synchronize_session=False)
            session.commit()
            typer.echo("已删除")
        elif orphans and dry_run:
            for o in orphans[:10]:
                typer.echo(f"  - ID={o.id} word_id={o.word_id} dim={o.dimension}")
            if len(orphans) > 10:
                typer.echo(f"  ... 及其他 {len(orphans) - 10} 条")
            typer.echo("（dry-run 模式，使用 --no-dry-run 执行删除）")
    finally:
        session.close()


@app.command()
def create_admin(
    email: str = typer.Argument(..., help="管理员邮箱"),
    confirm: bool = typer.Option(False, "--confirm", help="跳过确认提示"),
):
    """创建或提升用户为 admin 角色。"""
    if "@" not in email:
        typer.echo("错误: 邮箱格式无效（缺少 @）", err=True)
        raise typer.Exit(code=1)

    if not confirm:
        typer.confirm(f"确认将 {email} 设为 admin？", abort=True)

    from vocab_qc.core.db import SyncSessionLocal
    from vocab_qc.core.models.user import User

    session = SyncSessionLocal()
    try:
        user = session.query(User).filter_by(email=email).first()
        if user is None:
            name = email.split("@")[0]
            user = User(email=email, name=name, role="admin", is_active=True)
            session.add(user)
            action = "创建"
        elif user.role != "admin":
            user.role = "admin"
            action = "提升"
        else:
            typer.echo(f"{email} 已经是 admin")
            return
        session.commit()
        typer.echo(f"已{action} admin 用户: {email}")
    except Exception as e:
        session.rollback()
        typer.echo(f"操作失败: {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        session.close()


if __name__ == "__main__":
    app()
