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


if __name__ == "__main__":
    app()
