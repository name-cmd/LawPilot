import { request } from './client'
import type { CheckInputResponse } from './types'

export function checkInput(query: string, privacyConfirmed: boolean) {
  return request<CheckInputResponse>('/api/check-input', {
    method: 'POST',
    body: JSON.stringify({
      query,
      privacy_confirmed: privacyConfirmed === true,
    }),
  })
}

export function autoTitle(query: string) {
  return request<{ title: string }>('/api/session-title', {
    method: 'POST',
    body: JSON.stringify({ query }),
  })
}
