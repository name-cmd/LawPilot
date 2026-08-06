/**
 * 生成唯一 id（消息/会话用）。
 * 旧版格式：m_时间戳_随机串（后端按 message_id 注册核验任务，保持同一格式即可）
 */
export function uid(): string {
  return 'm_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7)
}

/** 会话 id 格式沿用旧版：s_时间戳 */
export function sessionId(): string {
  return 's_' + Date.now()
}
