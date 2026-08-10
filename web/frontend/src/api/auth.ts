import { request } from './client'
import type { LoginResponse, VerifyResponse } from './types'

export function login(username: string, password: string) {
  return request<LoginResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

/** 注册新用户：成功即自动登录（后端直接返回 token） */
export function register(username: string, password: string) {
  return request<LoginResponse>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export function verifyToken(token: string) {
  return request<VerifyResponse>('/api/auth/verify', {
    method: 'POST',
    body: JSON.stringify({ token }),
  })
}

export function logout(token: string) {
  return request<{ ok: boolean }>('/api/auth/logout', {
    method: 'POST',
    body: JSON.stringify({ token }),
  })
}
