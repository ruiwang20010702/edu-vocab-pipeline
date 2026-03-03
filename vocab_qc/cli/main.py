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


if __name__ == "__main__":
    app()
