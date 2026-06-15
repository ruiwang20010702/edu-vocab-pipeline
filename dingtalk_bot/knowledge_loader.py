"""加载 knowledge/ 下所有 .md，拼成单一知识库文本块，供 system prompt 使用。

MVP 不做向量检索：知识量小，整体塞进 prompt + 缓存锚点即可（见方案第 3 节）。
"""

from __future__ import annotations

from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"


def load_knowledge(knowledge_dir: Path | None = None) -> str:
    """读取知识目录下所有 .md（按文件名排序），拼成一段文本。"""
    directory = knowledge_dir or KNOWLEDGE_DIR
    files = sorted(directory.glob("*.md"))
    if not files:
        raise RuntimeError(f"知识库为空，未找到任何 .md: {directory}")
    blocks = [f"# 文件：{f.name}\n\n{f.read_text(encoding='utf-8').strip()}" for f in files]
    return "\n\n---\n\n".join(blocks)


def approx_tokens(text: str) -> int:
    """粗估 token 数（中英混排按 1.5 字符/token 兜底偏大估算）。"""
    return int(len(text) / 1.5)


if __name__ == "__main__":
    kb = load_knowledge()
    file_count = len(sorted(KNOWLEDGE_DIR.glob("*.md")))
    print(f"知识文件数: {file_count}")
    print(f"总字符数: {len(kb)}  约 {approx_tokens(kb)} tokens")
