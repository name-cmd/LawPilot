import { request } from './client'
import type { CheckInputResponse, ModelsResponse } from './types'

export function checkInput(query: string, privacyConfirmed: boolean) {
  return request<CheckInputResponse>('/api/check-input', {
    method: 'POST',
    body: JSON.stringify({
      query,
      privacy_confirmed: privacyConfirmed === true,
    }),
  })
}

/** 模型目录（7 个 API 模型 + 离线引擎状态 + 全局默认）——模型选择器/设置面板的数据源 */
export function fetchModels() {
  return request<ModelsResponse>('/api/models')
}

export function autoTitle(query: string) {
  return request<{ title: string }>('/api/session-title', {
    method: 'POST',
    body: JSON.stringify({ query }),
  })
}
