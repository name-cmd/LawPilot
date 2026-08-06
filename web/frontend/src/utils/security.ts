/**
 * 安全工具（原样迁移自旧版 index.html）。
 * 注意：Vue 模板自动转义，这里的 escapeHtml 仅在极少数
 * 非模板场景（如生成打印报告 HTML）使用。
 */

/** HTML 转义 */
export function escapeHtml(s: unknown): string {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/** 属性值转义 */
export function escapeAttr(s: unknown): string {
  return String(s).replace(/"/g, '&quot;')
}

/**
 * 对极度私密信息（身份证号 17 位数字+X、银行卡号 16-19 位）脱敏。
 * 身份证：保留前 6 后 4；银行卡：保留前 4 后 4。
 */
export function maskCriticalPii(text: unknown): string {
  const maskId = (s: string) =>
    s.length >= 14
      ? s.slice(0, 6) + '*'.repeat(s.length - 10) + s.slice(-4)
      : '*'.repeat(s.length)
  const maskBank = (s: string) =>
    s.length >= 8
      ? s.slice(0, 4) + '*'.repeat(s.length - 8) + s.slice(-4)
      : '*'.repeat(s.length)

  let out = String(text).replace(/\d{17}[\dXx]/g, maskId)
  out = out.replace(/\d{16,19}/g, maskBank)
  return out
}
