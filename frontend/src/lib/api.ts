/**
 * API 客户端 — 封装 fetch，自动注入 JWT + 错误处理。
 */

const BASE_URL = '/api'

class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail)
    this.name = 'ApiError'
  }
}

function getToken(): string | null {
  const raw = localStorage.getItem('auth')
  if (!raw) return null
  try {
    return JSON.parse(raw).access_token ?? null
  } catch {
    return null
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> ?? {}),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (res.status === 401) {
    localStorage.removeItem('auth')
    window.location.href = '/'
    throw new ApiError(401, '登录已过期')
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: '请求失败' }))
    throw new ApiError(res.status, body.detail ?? '请求失败')
  }

  if (res.status === 204) return undefined as T
  return res.json()
}

/* ===== 公开方法 ===== */

export const api = {
  get: <T>(path: string) => request<T>(path),

  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),

  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PATCH',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),

  delete: <T>(path: string) =>
    request<T>(path, { method: 'DELETE' }),

  upload: <T>(path: string, formData: FormData) =>
    request<T>(path, {
      method: 'POST',
      body: formData,
      headers: {}, // 让浏览器自动设置 multipart boundary
    }),
}

export { ApiError }
