"""P-H1: 公共 async-to-sync 桥接函数."""

import asyncio
import concurrent.futures


def run_async_in_sync(coro):
    """在同步上下文中运行协程。

    - 无 running loop → 直接 asyncio.run
    - 有 running loop → 在独立线程中 asyncio.run（避免嵌套 loop）
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
