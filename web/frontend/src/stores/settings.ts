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
    // ── 模型选择（阶段八）──────────────
    // 两级选择器第一级：'api'（API 调用）| 'local'（离线调用）
    modelProvider: 'api' as 'api' | 'local',
    // 第二级：'auto'（跟随全局默认）| 具体模型 id
    apiModel: 'auto' as string,
    // 设置面板的全局默认模型（Auto 跟随它；以后端解析结果为准）
    globalDefaultModel: 'qwen3.7-plus' as string,
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
