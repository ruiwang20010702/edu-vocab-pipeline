"""质检 CLI 命令."""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from vocab_qc.core.db import get_sync_session
from vocab_qc.core.services.qc_service import QcService

qc_app = typer.Typer(help="质检命令")
console = Console()


@qc_app.command("run")
def run_qc(
    layer: int = typer.Option(1, "--layer", "-l", help="质检层 (1 或 2)"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="范围，如 word_id:123"),
    dimension: Optional[str] = typer.Option(None, "--dim", "-d", help="维度筛选"),
    strategy: Optional[str] = typer.Option(None, "--strategy", help="AI 策略 (per_rule/unified)"),
):
    """运行质检."""
    session = get_sync_session()
    try:
        qc_service = QcService()

        if layer == 1:
            result = qc_service.run_layer1(session, scope=scope, dimension=dimension)
            session.commit()

            if result["run_id"] is None:
                console.print("[yellow]无内容项需要校验[/yellow]")
                return

            console.print("[green]Layer 1 校验完成[/green]")
            console.print(f"  运行 ID: {result['run_id']}")
            console.print(f"  总计: {result['total']}")
            console.print(f"  通过: {result['passed']}")
            console.print(f"  失败: {result['failed']}")

            # 自动入队失败项
            failed_count = qc_service.enqueue_failed_for_review(session, result["run_id"])
            session.commit()
            if failed_count > 0:
                console.print(f"  [yellow]{failed_count} 项已加入审核队列[/yellow]")
        else:
            console.print("[yellow]Layer 2 尚未实现[/yellow]")
    finally:
        session.close()


@qc_app.command("summary")
def qc_summary(
    run_id: Optional[str] = typer.Option(None, "--run-id", help="指定运行 ID"),
):
    """查看质检统计."""
    session = get_sync_session()
    try:
        qc_service = QcService()
        rows = qc_service.get_summary(session, run_id=run_id)

        table = Table(title="质检统计")
        table.add_column("规则", style="cyan")
        table.add_column("维度", style="green")
        table.add_column("总计", justify="right")
        table.add_column("通过", justify="right", style="green")
        table.add_column("失败", justify="right", style="red")
        table.add_column("通过率", justify="right")

        for row in rows:
            total = row["total"]
            passed = row["passed"]
            failed = total - passed
            rate = f"{passed / total * 100:.1f}%" if total > 0 else "N/A"
            table.add_row(row["rule_id"], row["dimension"], str(total), str(passed), str(failed), rate)

        console.print(table)
    finally:
        session.close()
