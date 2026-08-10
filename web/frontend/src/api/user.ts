/**
 * 用户数据服务端同步（阶段三：会话/收藏/资料/API Key 存服务端，换设备可恢复）。
 * 与后端 web/backend/main.py 的 /api/user/* 接口对齐。
 */
import { request } from './client'
import type { UserDataResponse, UserProfile } from './types'

/** 登录后拉取该用户会话与收藏（exists=false 表示服务端无数据 = 首次登录） */
export function fetchUserData(token: string) {
  return request<UserDataResponse>('/api/user/data', {
    method: 'POST',
    body: JSON.stringify({ token }),
  })
}

/** 整包保存会话与收藏（前端防抖提交） */
export function saveUserData(token: string, sessions: unknown[], favorites: unknown[]) {
  return request<{ ok: boolean }>('/api/user/data/save', {
    method: 'POST',
    body: JSON.stringify({ token, sessions, favorites }),
  })
}

/** 拉取该用户资料（含自配 API Key） */
export function fetchUserProfile(token: string) {
  return request<UserProfile>('/api/user/profile', {
    method: 'POST',
    body: JSON.stringify({ token }),
  })
}

/** 保存资料与 API Key（未提供的字段不覆盖） */
export function saveUserProfile(token: string, patch: Partial<UserProfile>) {
  return request<UserProfile>('/api/user/profile/save', {
    method: 'POST',
    body: JSON.stringify({ token, ...patch }),
  })
}
