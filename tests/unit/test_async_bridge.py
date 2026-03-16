"""P-H1: async bridge 测试."""

import asyncio

import pytest
from vocab_qc.core.async_bridge import run_async_in_sync


async def _async_add(a: int, b: int) -> int:
    await asyncio.sleep(0)
    return a + b


class TestRunAsyncInSync:
    def test_no_running_loop(self):
        """无 running loop → asyncio.run 直接执行。"""
        result = run_async_in_sync(_async_add(1, 2))
        assert result == 3

    def test_with_running_loop(self):
        """有 running loop → ThreadPoolExecutor 中执行。"""
        async def _wrapper():
            return run_async_in_sync(_async_add(3, 4))

        result = asyncio.run(_wrapper())
        assert result == 7

    def test_exception_propagation(self):
        """异步异常应正确传播。"""
        async def _fail():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            run_async_in_sync(_fail())
