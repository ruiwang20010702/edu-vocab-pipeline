import { useEffect, useRef } from 'react'

/**
 * 自动轮询 Hook：在 enabled 为 true 时以 intervalMs 间隔调用 callback。
 * - Tab 隐藏时暂停，Tab 可见时立即执行一次 + 重新启动
 * - 初始启动时不立即调用（页面自身 useEffect 负责首次加载）
 * - 通过 useRef 始终使用最新 callback，避免闭包过期
 */
export function usePolling(
  callback: () => void | Promise<void>,
  intervalMs: number,
  enabled: boolean = true,
): void {
  const savedCallback = useRef(callback)

  // 始终保持最新 callback
  useEffect(() => {
    savedCallback.current = callback
  }, [callback])

  useEffect(() => {
    if (!enabled) return

    let intervalId: ReturnType<typeof setInterval> | null = null

    const start = () => {
      if (intervalId !== null) return
      intervalId = setInterval(() => {
        savedCallback.current()
      }, intervalMs)
    }

    const stop = () => {
      if (intervalId !== null) {
        clearInterval(intervalId)
        intervalId = null
      }
    }

    const handleVisibilityChange = () => {
      if (document.hidden) {
        stop()
      } else {
        // Tab 可见时立即执行一次 + 重新启动
        savedCallback.current()
        start()
      }
    }

    start()
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      stop()
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [intervalMs, enabled])
}
