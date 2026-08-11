import { defineStore } from 'pinia'

export type ThemeMode = 'light' | 'dark' | 'system'
export type FontSizeMode = 'standard' | 'large' | 'xlarge'
export type CitationStyle = 'concise' | 'full'

export interface TrustDimensionConfig {
  key: string
  label: string
  enabled: boolean
}

/**
 * 全局偏好设置（唯一的主题驱动源）。
 * 主题切换会同时做三件事：
 *   1. 切换 <html> 的 .dark 类 → 驱动 Tailwind 的 dark: 变体与令牌覆盖
 *   2. App.vue 里 isDark 响应式切换 Naive UI 的 darkTheme
 *   3. 跟随系统时监听 matchMedia('(prefers-color-scheme: dark)')
 * 一个开关，双端联动。
 */
export const useSettingsStore = defineStore('settings', {
  state: () => ({
    // ── 通用 ─────────────────────────────────────────────
    theme: 'light' as ThemeMode,
    fontSize: 'standard' as FontSizeMode,
    language: 'zh-CN' as string,

    // ── 模型与推理 ───────────────────────────────────────
    // 两级选择器第一级：'api'（API 调用）| 'local'（离线调用）
    modelProvider: 'api' as 'api' | 'local',
    // 第二级：'auto'（跟随全局默认）| 具体模型 id
    apiModel: 'auto' as string,
    // 设置面板的全局默认模型（Auto 跟随它；以后端解析结果为准）
    globalDefaultModel: 'qwen3.7-plus' as string,
    // 深度思考模式（记录前端偏好，实际是否生效由模型支持决定）
    thinkingMode: false,

    // ── 检索与引用（原“问答偏好”的实质内容）──────────────
    useRag: true,
    enableConsistency: true,
    enableNli: true,
    nConsistencySamples: 2,
    citationStyle: 'full' as CitationStyle,

    // ── 可信评估 ─────────────────────────────────────────
    enableTrustEval: true,
    trustDimensions: [
      { key: 'factual_accuracy', label: '事实准确性', enabled: true },
      { key: 'legal_basis', label: '法律依据', enabled: true },
      { key: 'logical_consistency', label: '逻辑一致性', enabled: true },
      { key: 'timeliness', label: '时效性', enabled: true },
      { key: 'completeness', label: '完整性', enabled: true },
      { key: 'safety', label: '安全性', enabled: true },
    ] as TrustDimensionConfig[],

    // ── 隐私与安全 ───────────────────────────────────────
    privacyConfirmed: false,
    privacyAlert: true,
  }),
  getters: {
    /** 当前实际生效的主题：system 时跟随系统偏好 */
    effectiveTheme(): 'light' | 'dark' {
      if (this.theme === 'system') {
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
      }
      return this.theme
    },
    /** 是否启用六维可信评估（任一维度关闭仅影响展示，不影响后端评分） */
    isTrustEvalEnabled(): boolean {
      return this.enableTrustEval && this.trustDimensions.some((d) => d.enabled)
    },
    /** 字体大小对应的根字号偏移（px） */
    fontSizeOffset(): number {
      return { standard: 0, large: 2, xlarge: 4 }[this.fontSize]
    },
  },
  actions: {
    setTheme(mode: ThemeMode) {
      this.theme = mode
      this.applyTheme()
    },
    toggleTheme() {
      this.theme = this.theme === 'dark' ? 'light' : 'dark'
      this.applyTheme()
    },
    applyTheme() {
      document.documentElement.classList.toggle('dark', this.effectiveTheme === 'dark')
    },
    applyFontSize() {
      document.documentElement.style.fontSize = `${16 + this.fontSizeOffset}px`
    },
    /** 切换指定可信评估维度的启用状态 */
    toggleTrustDimension(key: string) {
      const dim = this.trustDimensions.find((d) => d.key === key)
      if (dim) dim.enabled = !dim.enabled
    },
  },
  persist: {
    key: 'lawtrust_settings_v2',
  },
})
