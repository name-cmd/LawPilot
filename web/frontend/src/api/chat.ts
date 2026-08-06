import { normalizeError } from './client'
import type { ChatRequest } from './types'

/**
 * 流式问答：POST /api/chat/stream，把响应体交给解析器（SSE）。
 * 非 2xx 时抛出归一化 ApiError（与 request 一致）。
 * 返回 reader 供调用方解析；signal 用于取消（AbortController）。
 */
export async function streamChat(
  req: ChatRequest,
  signal?: AbortSignal,
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  let res: Response
  try {
    res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
      signal,
    })
  } catch {
    throw new Error('无法连接服务器，请确认后端服务已启动')
  }
  if (!res.ok) {
    let detail: unknown = null
    try {
      detail = (await res.json()).detail
    } catch {
      /* ignore */
    }
    throw normalizeError(detail)
  }
  if (!res.body) throw new Error('浏览器不支持流式响应')
  return res.body.getReader()
}

/** 非流式降级：POST /api/chat */
export async function chatSync(
  req: ChatRequest,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  let res: Response
  try {
    res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
      signal,
    })
  } catch {
    throw new Error('无法连接服务器，请确认后端服务已启动')
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw normalizeError(data.detail)
  }
  return data
}
