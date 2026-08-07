/**
 * 与后端 web/backend/schemas.py 对齐的 TS 类型。
 * 字段名直接沿用后端的 snake_case（与 JSON 完全一致，不做映射层，减少出错面）。
 */

// ── 认证 ───────────────────────────────────────────────
export interface LoginResponse {
  token: string
  username: string
  display_name: string
}

export interface VerifyResponse {
  valid: boolean
  display_name?: string
}

// ── 输入守卫 / 隐私检查 ────────────────────────────────
export interface CheckInputResponse {
  allowed: boolean
  refused: boolean
  refusal_message?: string
  sanitized_query: string
  has_pii: boolean
  pii_types: string[]
  critical_pii_masked: boolean
  needs_privacy_confirm: boolean
  privacy_warning?: string
}

// ── 文档上传 ───────────────────────────────────────────
export interface DocumentExtractResponse {
  filename: string
  text: string
  format: string
  char_count: number
  page_count?: number
  extraction_methods?: string[]
  warnings: string[]
}

export interface SupportedFormatsResponse {
  extensions: string[]
  max_upload_mb: number
  max_attachments: number
}

// ── 聊天 ───────────────────────────────────────────────
export interface HistoryItem {
  role: 'user' | 'assistant'
  content: string
}

export interface UserDocument {
  filename: string
  text: string
  format: string
  char_count: number
}

export interface ChatRequest {
  query: string
  message_id?: string
  history: HistoryItem[]
  user_documents: UserDocument[]
  use_rag: boolean
  enable_consistency: boolean
  enable_nli: boolean
  n_consistency_samples: number
  privacy_confirmed: boolean
  /** 模型选择：'auto' | 模型 id（如 'qwen3.7-plus'）| 'local'；缺省按 auto 处理 */
  model?: string
  /** 设置面板保存的全局默认模型 id（Auto 解析用，以后端为准） */
  global_model?: string
}

// ── 模型目录（/api/models）──────────────────────────────
export interface ApiModelInfo {
  id: string
  display_name: string
  provider: string
  price_tier: string
  capabilities: string
  is_default: boolean
  is_enabled: boolean
  thinking_supported: boolean
}

export interface LocalEngineInfo {
  available: boolean
  reason: string
}

export interface ModelsResponse {
  api_models: ApiModelInfo[]
  local_engine: LocalEngineInfo
  default_model: string
}

// 引用核验（对齐后端 citation_verifier 输出）
export interface RetrievedArticle {
  law_name: string
  article_num: string
  /** 0~1 相关度（旧版换算成百分比展示） */
  relevance_score?: number
  content?: string
  /** effective / repealed / amended 等（非 effective 视为已废止） */
  status?: string
  superseded_by?: string
  effective_date?: string
}

export interface ExtractedCitation {
  text?: string
  /** 模型论述摘录（对比盒左栏） */
  quoted_text?: string
  arguing_sentence?: string
  /** 法条对照原文（对比盒右栏） */
  reference_excerpt?: string
  actual_content?: string
  verdict: string
  /** 0~1 内容吻合度 */
  content_match_score?: number
  in_retrieved_context?: boolean
  validity?: {
    effective: boolean
    status: string
    repeal_date?: string
    superseded_by?: string
    warning_message?: string
  }
  severity?: 'error' | 'warning' | 'ok'
}

export interface ImplicitClaim {
  claim?: string
  text?: string
  supported?: boolean
  support_score?: number
}

export interface CitationVerification {
  extracted_citations: ExtractedCitation[]
  implicit_claims: ImplicitClaim[]
  overall_citation_score: number
  summary: string
}

// 六维可信评估（对齐 src/trust_eval/legal_trust_scorer.py 输出）
export interface RadarItem {
  name: string
  value: number
  key: string
}

export interface DimensionCheck {
  type?: string
  label: string
  passed?: number | boolean
  total?: number
  severity?: string
}

export interface DimensionFormula {
  expression?: string
  inputs?: { name: string; value: number; weight: number; source?: string }[]
  result?: number
}

export interface DimensionDetail {
  key: string
  label: string
  /** pending 中为 null */
  score: number | null
  /** 0~1 权重（展示时乘 100 变百分比） */
  weight: number
  contribution?: number | null
  method?: string
  status: string
  checks: DimensionCheck[]
  formula?: DimensionFormula
  evidence: string[]
  evidence_summary?: string
  /** 跳转目标 tab：citations / articles */
  detail_ref?: string
  pending?: boolean
}

export interface TrustResult {
  /** pending 中为 null */
  overall_score: number | null
  trust_level: string
  advice: string
  radar_data: RadarItem[]
  dimension_details: DimensionDetail[]
  score_contributions: { label: string; contribution: number | null }[]
  weak_dimensions: { key: string; label: string; score: number }[]
  evaluated_at?: string
  verification_status?: string
}

// 回答的消息 meta（存进消息对象，右侧详情面板与角标消费）
export interface MessageMeta {
  intent?: { intent?: string; [k: string]: unknown }
  rag_used?: boolean
  retrieved_articles?: RetrievedArticle[]
  citation_verification?: CitationVerification
  consistency?: unknown
  trust?: TrustResult | null
  validity_warnings?: string[]
  regeneration_attempts?: number
  /** pending=核验中；complete=核验完成；error=核验失败（退出"核验中"，展示已有初步评估） */
  verification_status?: 'pending' | 'complete' | 'error'
  refused?: boolean
  /** 实际使用的模型（后端 Auto 解析后落定） */
  model_id?: string
  model_name?: string
}

// ── SSE 事件（/api/chat/stream）─────────────────────────
export interface MetaEvent {
  intent?: MessageMeta['intent']
  rag_used?: boolean
  retrieved_articles?: RetrievedArticle[]
  citation_verification?: CitationVerification
  /** 首事件必发：实际使用的模型 */
  model_id?: string
  model_name?: string
}

export interface DoneEvent {
  answer?: string
  message_id?: string
  trust?: TrustResult | null
  non_legal?: boolean
  intent?: MessageMeta['intent']
  model_id?: string
  model_name?: string
}

export interface ErrorEvent {
  message: string
}

export type SSEEventMap = {
  meta: MetaEvent
  token: { content: string }
  done: DoneEvent
  error: ErrorEvent
}

// ── WebSocket 核验推送（verification_worker.py）──────────
export interface VerificationComplete {
  type: 'verification_complete'
  message_id: string
  citation_verification: CitationVerification
  consistency: unknown
  trust: TrustResult
  validity_warnings: string[]
  regeneration_attempts: number
}

export interface VerificationError {
  type: 'verification_error'
  message_id: string
  error: string
}
