"""内容生成器包."""

from pathlib import Path


def _find_project_root() -> Path:
    """向上查找包含 pyproject.toml 的目录作为项目根."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    raise RuntimeError(
        f"Cannot locate pyproject.toml within 10 levels of {Path(__file__)}"
    )
