/**
 * fetch 统一封装。
 * 后端错误有三种形态（见 web/backend/main.py 的约定），这里归一成一种：
 *   - detail 是字符串          → 直接展示
 *   - detail 是 {code,message} → 转成带 code 的 ApiError（privacy_confirm_required / refused）
 *   - detail 是数组（422 校验）→ 取每项的 .msg 拼接
 * 网络异常单独归为 code: 'network'。
 */

export type ApiErrorCode =
  | 'privacy_confirm_required'
  | 'refused'
  | 'validation'
  | 'network'

export class ApiError extends Error {
  code?: ApiErrorCode
  piiTypes?: string[]
  sanitizedQuery?: string

  constructor(message: string, opts?: { code?: ApiErrorCode; piiTypes?: string[]; sanitizedQuery?: string }) {
    super(message)
    this.name = 'ApiError'
    this.code = opts?.code
    this.piiTypes = opts?.piiTypes
    this.sanitizedQuery = opts?.sanitizedQuery
  }
}

export function isApiError(e: unknown, code?: ApiErrorCode): e is ApiError {
  return e instanceof ApiError && (code === undefined || e.code === code)
}

export function normalizeError(detail: unknown): ApiError {
  if (typeof detail === 'string') return new ApiError(detail)
  if (Array.isArray(detail)) {
    // 422 校验错误：detail 为数组
    const msgs = detail.map((d: unknown) => {
      const item = d as { msg?: string }
      return item?.msg || JSON.stringify(d)
    })
    return new ApiError(msgs.join('；'), { code: 'validation' })
  }
  if (detail && typeof detail === 'object') {
    const d = detail as { code?: string; message?: string; pii_types?: string[]; sanitized_query?: string }
    if (d.code === 'privacy_confirm_required') {
      return new ApiError(d.message || '需要确认隐私信息', {
        code: 'privacy_confirm_required',
        piiTypes: d.pii_types,
        sanitizedQuery: d.sanitized_query,
      })
    }
    if (d.code === 'refused') return new ApiError(d.message || '请求被拒绝', { code: 'refused' })
    if (d.message) return new ApiError(d.message)
  }
  return new ApiError('请求失败')
}

/** 通用 JSON 请求。非 2xx 时把 detail 归一为 ApiError 抛出。 */
export async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch {
    throw new ApiError('无法连接服务器，请确认后端服务已启动', { code: 'network' })
  }
  if (!res.ok) {
    let detail: unknown = null
    try {
      detail = (await res.json()).detail
    } catch {
      /* 非 JSON 响应，保持 detail = null */
    }
    throw normalizeError(detail)
  }
  return (await res.json()) as T
}
