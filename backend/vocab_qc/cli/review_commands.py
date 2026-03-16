"""审核 CLI 命令."""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from vocab_qc.core.db import get_sync_session
from vocab_qc.core.services.review_service import ReviewService

review_app = typer.Typer(help="审核命令")
console = Console()


@review_app.command("list")
def list_reviews(
    dimension: Optional[str] = typer.Option(None, "--dim", "-d", help="维度筛选"),
    limit: int = typer.Option(20, "--limit", "-n", help="显示数量"),
):
    """查看待审核队列."""
    session = get_sync_session()
    try:
        service = ReviewService()
        items, _total = service.get_pending_reviews(session, dimension=dimension, limit=limit)

        if not items:
            console.print("[green]无待审核项[/green]")
            return

        table = Table(title="待审核队列")
        table.add_column("ID", style="cyan")
        table.add_column("内容项ID")
        table.add_column("维度", style="green")
        table.add_column("原因", style="yellow")
        table.add_column("优先级", justify="right")
        table.add_column("创建时间")

        for item in items:
            table.add_row(
                str(item.id),
                str(item.content_item_id),
                item.dimension,
                item.reason,
                str(item.priority),
                str(item.created_at) if item.created_at else "",
            )

        console.print(table)
    finally:
        session.close()


@review_app.command("approve")
def approve(review_id: int = typer.Argument(..., help="审核项 ID"), reviewer: str = typer.Option("cli_user", "--by")):
    """通过审核."""
    session = get_sync_session()
    try:
        service = ReviewService()
        service.approve(session, review_id, reviewer=reviewer)
        session.commit()
        console.print(f"[green]审核项 #{review_id} 已通过[/green]")
    finally:
        session.close()


@review_app.command("regenerate")
def regenerate(
    review_id: int = typer.Argument(..., help="审核项 ID"),
    reviewer: str = typer.Option("cli_user", "--by"),
):
    """触发重新生成."""
    session = get_sync_session()
    try:
        service = ReviewService()
        result = service.regenerate(session, review_id, reviewer=reviewer)
        session.commit()

        if result["success"]:
            console.print(f"[green]{result['message']}[/green]")
        else:
            console.print(f"[red]{result['message']}[/red]")
    finally:
        session.close()


@review_app.command("edit")
def manual_edit(
    review_id: int = typer.Argument(..., help="审核项 ID"),
    content: str = typer.Argument(..., help="新内容"),
    reviewer: str = typer.Option("cli_user", "--by"),
):
    """人工修改内容."""
    session = get_sync_session()
    try:
        service = ReviewService()
        service.manual_edit(session, review_id, reviewer=reviewer, new_content=content)
        session.commit()
        console.print(f"[green]审核项 #{review_id} 已修改[/green]")
    finally:
        session.close()
