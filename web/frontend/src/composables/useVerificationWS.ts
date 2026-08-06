import type { VerificationComplete, VerificationError } from '@/api/types'

/**
 * 异步核验 WebSocket 管理（/ws/verification/{message_id}）。
 * module 级 Map 跨组件共享连接；后端 task_registry 有结果缓存，
 * 连接后若任务已完成会立即重放结果，因此重试只兜网络抖动（最多 2 次）。
 */
const sockets = new Map<string, WebSocket>()

export interface VerificationHandlers {
  onComplete: (data: VerificationComplete) => void
  onError?: (err: string) => void
}

export function useVerificationWS() {
  function connect(messageId: string, handlers: VerificationHandlers): void {
    // 先关同 id 的旧连接（旧版同款行为：重答时复用）
    const existing = sockets.get(messageId)
    if (existing) {
      try {
        existing.close()
      } catch {
        /* ignore */
      }
      sockets.delete(messageId)
    }

    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${location.host}/ws/verification/${messageId}`)
    sockets.set(messageId, ws)

    let retries = 0
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as VerificationComplete | VerificationError
        if (data.type === 'verification_complete') {
          handlers.onComplete(data)
          close(messageId) // 收到结果即关闭
        } else if (data.type === 'verification_error') {
          handlers.onError?.(data.error || '未知错误')
          close(messageId)
        }
      } catch {
        /* 忽略坏帧 */
      }
    }
    // 网络抖动重试：1s / 3s 各一次
    ws.onerror = () => {
      if (ws.readyState === WebSocket.CLOSED && retries < 2) {
        retries += 1
        setTimeout(() => {
          if (sockets.get(messageId) === ws) connect(messageId, handlers)
        }, retries === 1 ? 1000 : 3000)
      }
    }
  }

  function close(messageId: string): void {
    const ws = sockets.get(messageId)
    if (ws) {
      try {
        ws.close()
      } catch {
        /* ignore */
      }
      sockets.delete(messageId)
    }
  }

  function closeAll(): void {
    for (const ws of sockets.values()) {
      try {
        ws.close()
      } catch {
        /* ignore */
      }
    }
    sockets.clear()
  }

  return { connect, close, closeAll }
}
