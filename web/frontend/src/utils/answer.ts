/**
 * 回答内容工具（原样迁移自旧版 index.html）。
 * 后端回答带 【结论】/【法律分析】/【依据法条】 三段式结构，
 * 这里把纯文本拆成章节，便于分块渲染。
 */

export interface AnswerSection {
  title: string
  body: string
}

/** 正则切分三段式回答；没有三段式结构时返回 null（整体渲染） */
export function parseAnswerSections(text: string): AnswerSection[] | null {
  const sections = [
    { key: '结论', re: /【结论】\s*([\s\S]*?)(?=【法律分析】|【依据法条】|$)/ },
    { key: '法律分析', re: /【法律分析】\s*([\s\S]*?)(?=【依据法条】|$)/ },
    { key: '依据法条', re: /【依据法条】\s*([\s\S]*)/ },
  ]
  if (!sections.some((s) => s.re.test(text))) return null
  return sections
    .map((s) => {
      const m = text.match(s.re)
      return m ? { title: s.key, body: m[1].trim() } : null
    })
    .filter((x): x is AnswerSection => Boolean(x))
}

/** 引用核验的裁决样式归类（旧版 verdictClass 逻辑） */
export function verdictClass(v?: string): 'ok' | 'warn' | 'bad' {
  if (!v) return 'bad'
  if (v.includes('✅') || v.includes('准确')) return 'ok'
  if (v.includes('⚠')) return 'warn'
  return 'bad'
}

/** 是否为法律类回答（决定是否展示详情面板与可信角标） */
export function isLegalAnalysisMeta(meta?: { intent?: { intent?: string }; refused?: boolean }): boolean {
  if (!meta || meta.refused) return false
  const intent = meta.intent?.intent
  if (intent === 'greeting' || intent === 'general_non_legal') return false
  return true
}

/** 核验是否仍在进行中（pending 或 trust.verification_status === 'pending'） */
export function isVerificationPending(meta?: {
  verification_status?: string
  trust?: { verification_status?: string } | null
}): boolean {
  if (!meta) return false
  if (meta.verification_status === 'pending') return true
  return !!(meta.trust && meta.trust.verification_status === 'pending')
}
