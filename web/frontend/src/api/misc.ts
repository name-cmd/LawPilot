import { ApiError, normalizeError, request } from './client'
import type {
  CheckInputResponse,
  DocumentExtractResponse,
  ModelsResponse,
  SupportedFormatsResponse,
} from './types'

export function checkInput(query: string, privacyConfirmed: boolean) {
  return request<CheckInputResponse>('/api/check-input', {
    method: 'POST',
    body: JSON.stringify({
      query,
      privacy_confirmed: privacyConfirmed === true,
    }),
  })
}

/** 模型目录（7 个 API 模型 + 离线引擎状态 + 全局默认）——模型选择器/设置面板的数据源 */
export function fetchModels() {
  return request<ModelsResponse>('/api/models')
}

export function autoTitle(query: string) {
  return request<{ title: string }>('/api/session-title', {
    method: 'POST',
    body: JSON.stringify({ query }),
  })
}

/** 文档上传（multipart）。不能走 JSON 封装的 request（会强制 Content-Type），
 *  这里用原生 fetch，但错误归一化复用 client 的 normalizeError（与其它接口一致）。 */
export async function uploadDocument(file: File): Promise<DocumentExtractResponse> {
  const form = new FormData()
  form.append('file', file)
  let res: Response
  try {
    res = await fetch('/api/documents/extract', { method: 'POST', body: form })
  } catch {
    throw new ApiError('无法连接服务器，请确认后端服务已启动', { code: 'network' })
  }
  if (!res.ok) {
    let detail: unknown = null
    try {
      detail = (await res.json()).detail
    } catch {
      /* 非 JSON 响应 */
    }
    throw normalizeError(detail)
  }
  return (await res.json()) as DocumentExtractResponse
}

/** 上传限制（扩展名 / 单文件上限 / 附件数上限），用于前端按钮 title 与拦截提示 */
export function fetchSupportedFormats() {
  return request<SupportedFormatsResponse>('/api/documents/supported-formats')
}
