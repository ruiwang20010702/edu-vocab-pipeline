"""Profile ExportService.export_to_excel on the live dev database.

Usage:
    PYTHONPATH=backend python3 scripts/profile_export.py

Outputs:
    - scripts/profile_export.html (火焰图，浏览器打开)
    - 终端打印 Top 函数耗时
    - 终端打印总耗时 / Excel 字节数 / 内存峰值（tracemalloc）
"""
from __future__ import annotations

import os
import sys
import time
import tracemalloc
from pathlib import Path

from pyinstrument import Profiler

from vocab_qc.core.db import SyncSessionLocal
from vocab_qc.core.services.export_service import ExportService

OUT_HTML = Path(__file__).parent / "profile_export.html"


def main() -> int:
    session = SyncSessionLocal()
    service = ExportService()

    tracemalloc.start()
    profiler = Profiler(interval=0.001, async_mode="disabled")

    t0 = time.perf_counter()
    profiler.start()
    try:
        # P-M2 之后 export_to_excel 返回临时文件 Path
        xlsx_path: Path = service.export_to_excel(session)
    finally:
        profiler.stop()
        elapsed = time.perf_counter() - t0
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        session.close()

    excel_bytes = xlsx_path.stat().st_size
    # 临时文件读完大小就清理，避免 /tmp 累积
    try:
        os.unlink(xlsx_path)
    except OSError:
        pass

    OUT_HTML.write_text(profiler.output_html(), encoding="utf-8")

    print("=" * 70)
    print(f"  Total elapsed         : {elapsed:.2f} s")
    print(f"  Excel size            : {excel_bytes / 1024:.1f} KB")
    print(f"  Memory peak (traced)  : {peak / 1024 / 1024:.1f} MB")
    print(f"  HTML flame graph      : {OUT_HTML}")
    print("=" * 70)
    print(profiler.output_text(unicode=True, color=False, show_all=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
