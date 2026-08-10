import { ref } from 'vue'
import { streamChat, chatSync } from '@/api/chat'
import type { AgentStatusEvent, ChatRequest, DoneEvent, MetaEvent } from '@/api/types'

/** 是否用户主动取消（AbortController.abort），取消不触发降级 */
export function isAbortError(e: unknown): boolean {
  return e instanceof DOMException && e.name === 'AbortError'
}

/**
 * SSE 流式解析器（原样迁移自旧版 parseSSEStream）。
 * 按 \n\n 分帧，取 event:/data: 行，data 是 JSON。
 */
export async function parseSSE(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onEvent: (event: string, data: unknown) => void,
): Promise<void> {
  const decoder = new TextDecoder()
  let buffer = ''
  return reader.read().then(function process({ done, value }): Promise<void> {
    if (done) return Promise.resolve()
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''
    for (const part of parts) {
      const lines = part.split('\n')
      let event = 'message'
      let data = ''
      for (const line of lines) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data = line.slice(5).trim()
      }
      if (data) {
        try {
          onEvent(event, JSON.parse(data))
        } catch {
          /* 忽略损坏帧 */
        }
      }
    }
    return reader.read().then(process)
  })
}

export interface StreamCallbacks {
  onMeta?: (m: MetaEvent) => void
  onToken?: (text: string) => void
  /** 智能体工具调用状态事件（running/done/error/generating） */
  onAgentStatus?: (s: AgentStatusEvent) => void
  onDone?: (d: DoneEvent) => void
  /** 流式失败、开始降级前的钩子（调用方清空半截回答、改思考文字） */
  onFallbackStart?: () => void
  /** 降级 /api/chat 成功返回 */
  onFallback?: (data: Record<string, unknown>) => void
}

/**
 * 一次问答请求的完整生命周期：SSE 流式 → 失败自动降级 /api/chat。
 * 行为与旧版 askStream + askFallback 对齐：
 *   - SSE error 事件或 fetch 抛错 → 降级（用户取消除外）
 *   - AbortError（cancel()）→ 原样抛出，不降级、不留半截消息
 */
export function useChatStream() {
  const controller = ref<AbortController | null>(null)

  function cancel() {
    controller.value?.abort()
  }

  async function runStream(req: ChatRequest, cb: StreamCallbacks): Promise<void> {
    const ac = new AbortController()
    controller.value = ac
    const reader = await streamChat(req, ac.signal)
    await parseSSE(reader, (event, data) => {
      if (event === 'meta') cb.onMeta?.(data as MetaEvent)
      else if (event === 'token') cb.onToken?.((data as { content?: string }).content || '')
      else if (event === 'agent_status') cb.onAgentStatus?.(data as AgentStatusEvent)
      else if (event === 'done') cb.onDone?.(data as DoneEvent)
      else if (event === 'error') {
        throw new Error((data as { message?: string }).message || '生成失败')
      }
    })
  }

  /** 主入口：流式 + 降级 */
  async function ask(req: ChatRequest, cb: StreamCallbacks): Promise<void> {
    try {
      await runStream(req, cb)
    } catch (e) {
      if (isAbortError(e)) throw e // 用户取消，不做降级
      console.warn('[useChatStream] 流式失败，降级 /api/chat', e)
      cb.onFallbackStart?.()
      const data = await chatSync(req)
      cb.onFallback?.(data)
    }
  }

  return { ask, cancel }
}
