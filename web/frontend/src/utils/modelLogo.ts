/**
 * 模型品牌 logo 工具：按模型 id 前缀映射品牌，生成 public/logos/ 下的 logo 图片 URL。
 * 共用方：ModelSelector（模型选择器列表 / 触发器）与 ChatMessage（回答气泡模型角标）。
 * 图片由 scripts/download_model_logos.py 下载到 web/frontend/public/logos/<brand>.png。
 */

/** 供应商 logo：按模型 id 前缀映射品牌（后端 provider 字段全是 dashscope，无法区分品牌） */
const BRAND_PREFIXES: ReadonlyArray<readonly [string, string]> = [
  ['qwen', 'qwen'], // qwen3.7-plus / qwen-turbo / qwen3.7-max
  ['deepseek', 'deepseek'], // deepseek-v4-flash-0731 / deepseek-v4-pro
  ['kimi', 'kimi'], // kimi-k2.6
  ['glm', 'glm'], // glm-5.2
]

/** 模型 id → 品牌名；未知品牌返回 null（不显示 logo，仅文字） */
export function brandOf(id?: string | null): string | null {
  if (!id) return null
  const hit = BRAND_PREFIXES.find(([prefix]) => id.includes(prefix))
  return hit ? hit[1] : null
}

/** 品牌 → 图片 URL：public/ 目录构建时原样复制进 dist，用 BASE_URL 兼容开发(/)与生产(/ui/) */
export function logoUrl(brand: string | null): string | undefined {
  return brand ? `${import.meta.env.BASE_URL}logos/${brand}.png` : undefined
}

/** 模型 id → logo URL（undefined = 该模型无品牌 logo） */
export function modelLogo(id?: string | null): string | undefined {
  return logoUrl(brandOf(id))
}

/** 图片加载失败（缺图/网络错误）时隐藏该 img，保证只显示文字、不破坏布局 */
export function imgError(e: Event): void {
  ;(e.target as HTMLImageElement).style.display = 'none'
}
