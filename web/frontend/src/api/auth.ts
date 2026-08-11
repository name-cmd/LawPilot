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

/** 修改密码：校验旧密码 → 重新哈希 → 吊销该用户其他设备的登录 */
export function changePassword(token: string, oldPassword: string, newPassword: string) {
  return request<{ ok: boolean; revoked_devices: number }>('/api/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ token, old_password: oldPassword, new_password: newPassword }),
  })
}
