import type { GlobalThemeOverrides } from 'naive-ui'

/**
 * Naive UI 主题微调：让组件主色与我们的品牌蓝一致。
 * 暗色模式由 n-config-provider 的 darkTheme 自动处理，
 * 这里只覆盖品牌色、圆角等设计令牌。
 */
export const naiveThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#1a5fb4',
    primaryColorHover: '#2a6fc4',
    primaryColorPressed: '#164a8f',
    primaryColorSuppl: '#2a6fc4',
    borderRadius: '8px',
    fontFamily:
      '"PingFang SC", "Microsoft YaHei", "Segoe UI", "Helvetica Neue", Arial, sans-serif',
  },
}
