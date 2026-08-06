import { defineStore } from 'pinia'

export type ThemeMode = 'light' | 'dark'

/**
 * 全局偏好设置（唯一的主题驱动源）。
 * 主题切换会同时做两件事：
 *   1. 切换 <html> 的 .dark 类 → 驱动 Tailwind 的 dark: 变体与令牌覆盖
 *   2. App.vue 里 isDark 响应式切换 Naive UI 的 darkTheme
 * 一个开关，双端联动。
 */
export const useSettingsStore = defineStore('settings', {
  state: () => ({
    theme: 'light' as ThemeMode,
    // 问答偏好（对应旧版页面上 RAG / 自一致性两个开关）
    useRag: true,
    enableConsistency: true,
    enableNli: true,
    nConsistencySamples: 2,
    privacyConfirmed: false,
  }),
  actions: {
    toggleTheme() {
      this.theme = this.theme === 'dark' ? 'light' : 'dark'
      this.applyTheme()
    },
    applyTheme() {
      document.documentElement.classList.toggle('dark', this.theme === 'dark')
    },
  },
  persist: {
    key: 'lawtrust_settings_v1',
  },
})
