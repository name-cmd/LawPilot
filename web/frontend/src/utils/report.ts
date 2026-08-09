/**
 * 可信评估报告导出（纯前端生成，移植自 legacy/index.html 导出功能）。
 * 流程：导出模式勾选法律问答 → 组装整页 HTML → window.open 新窗口 →
 * document.write → w.print()（打印对话框「另存为 PDF」）。无后端接口。
 * 六维评分用纯 CSS 横向条形图（不依赖 ECharts），报告 HTML 自包含、离线可打印。
 */
import { escapeHtml } from '@/utils/security'
import { isLegalAnalysisMeta } from '@/utils/answer'
import { useAuthStore } from '@/stores/auth'
import type { Message, Session } from '@/stores/sessions'
import type { CitationVerification, RadarItem, TrustResult } from '@/api/types'

/** 可导出的消息：助手消息 + 已生成完成 + 法律类回答（loading/拒答不可导出） */
export function getExportableMessages(session: Session | null): Message[] {
  if (!session) return []
  return session.messages.filter(
    (m) => m.role === 'assistant' && !m.loading && isLegalAnalysisMeta(m.meta),
  )
}

/** 找到该助手消息的前一条用户消息（报告「用户问」字段） */
export function getPairedUserMessage(session: Session, msg: Message): Message | null {
  const idx = session.messages.findIndex((m) => m.id === msg.id)
  if (idx <= 0) return null
  const prev = session.messages[idx - 1]
  return prev.role === 'user' ? prev : null
}

/** 六维评分纯 CSS 横向条形图（legacy buildReportBarChart 语义） */
function buildReportBarChart(radarData: RadarItem[]): string {
  if (!radarData || !radarData.length) return ''
  return `<div style="margin:12px 0">${radarData
    .map(
      (d) => `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:12px">
      <span style="width:72px;text-align:right">${escapeHtml(d.name)}</span>
      <div style="flex:1;height:8px;background:#eee;border-radius:4px;overflow:hidden">
        <div style="width:${d.value}%;height:100%;background:#1a5fb4;border-radius:4px"></div>
      </div>
      <span>${d.value}</span>
    </div>`,
    )
    .join('')}</div>`
}

/** 单条问答 → 报告 section（用户问 / 回答 / 可信评估 / 六维评分 / 法条溯源 / 引用核验） */
function buildReportSection(msg: Message, session: Session): string {
  const userMsg = getPairedUserMessage(session, msg)
  const meta = msg.meta || {}
  const trust = (meta.trust ?? {}) as TrustResult
  const ts = new Date(msg.timestamp || Date.now()).toLocaleString('zh-CN')
  const radarData = (trust.radar_data || []).filter((d) => d.value != null)
  const dims = (trust.dimension_details || [])
    .map(
      (d) => `
    <tr><td>${escapeHtml(d.label)}</td><td>${d.score != null ? d.score : '—'}</td>
    <td style="font-size:11px;color:#666">${escapeHtml(d.evidence_summary || (d.evidence || []).join('；'))}</td></tr>`,
    )
    .join('')
  const articles =
    (meta.retrieved_articles || [])
      .map(
        (a) => `
    <div style="border-left:3px solid #1a5fb4;padding:8px 12px;margin-bottom:8px;background:#f0f4f8;font-size:12px">
      <strong>《${escapeHtml(a.law_name)}》${escapeHtml(a.article_num || '')}</strong>
      <div style="margin-top:4px;color:#444;white-space:pre-wrap">${escapeHtml((a.content || '').slice(0, 500))}</div>
    </div>`,
      )
      .join('') || '<p style="color:#999">无</p>'
  const cv = meta.citation_verification ?? ({} as CitationVerification)
  const citations =
    (cv.extracted_citations || [])
      .map(
        (c) => `
    <div style="border:1px solid #e4e7ed;border-radius:6px;padding:8px;margin-bottom:6px;font-size:12px">
      <strong>${escapeHtml(c.text || '')}</strong>
      <div>${escapeHtml(c.verdict || '')}</div>
      ${c.content_match_score != null ? `<div>吻合度：${(c.content_match_score * 100).toFixed(0)}%</div>` : ''}
    </div>`,
      )
      .join('') || '<p style="color:#999">无显式引用</p>'

  return `
    <section class="report-section">
      <h3 class="report-section-title">问答记录 · ${escapeHtml(ts)}</h3>
      <p class="report-qa"><strong>用户问：</strong>${escapeHtml(userMsg ? userMsg.content : '（未知）')}</p>
      <div class="report-answer">${escapeHtml(msg.content)}</div>
      <h4 class="report-h4">可信评估</h4>
      <p class="report-score-line"><strong class="report-score">${trust.overall_score != null ? trust.overall_score : '—'}</strong>
      　${escapeHtml(trust.trust_level || '')} — ${escapeHtml(trust.advice || '')}</p>
      <h5 class="report-h5">六维评分</h5>
      ${buildReportBarChart(radarData)}
      <table class="report-table" border="1" cellpadding="6">
        <tr class="report-table-head"><th>维度</th><th>得分</th><th>证据说明</th></tr>
        ${dims || '<tr><td colspan="3">暂无</td></tr>'}
      </table>
      <h4 class="report-h4">法条溯源</h4>
      <div class="report-articles">${articles}</div>
      <h4 class="report-h4">引用核验</h4>
      <div class="report-citations">${citations}</div>
      ${cv.summary ? `<pre class="report-summary">${escapeHtml(cv.summary)}</pre>` : ''}
      <p class="report-disclaimer">仅供参考，不构成法律意见</p>
    </section>`
}

/** 打印样式（原样移植 legacy REPORT_PRINT_CSS：A4 页面、颜色打印、防分页截断） */
const REPORT_PRINT_CSS = `
  *, *::before, *::after { box-sizing: border-box; }
  html, body {
    margin: 0;
    padding: 0;
    height: auto;
    min-height: 0;
    background: #fff;
  }
  body {
    font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
    color: #222;
    line-height: 1.6;
    font-size: 13px;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  .report-root {
    max-width: 800px;
    margin: 0 auto;
    padding: 0 24px 16px;
  }
  .report-header {
    padding: 20px 0 12px;
    border-bottom: 1px solid #e4e7ed;
    margin-bottom: 20px;
  }
  .report-header h1 {
    margin: 0 0 6px;
    font-size: 22px;
    color: #1a3a5c;
  }
  .report-meta {
    font-size: 13px;
    color: #666;
    line-height: 1.7;
  }
  .report-section {
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px dashed #e4e7ed;
  }
  .report-section:last-child {
    margin-bottom: 0;
    padding-bottom: 0;
    border-bottom: none;
  }
  .report-section-title {
    color: #1a3a5c;
    border-bottom: 1px solid #e4e7ed;
    padding-bottom: 6px;
    margin: 0 0 10px;
    font-size: 15px;
    break-after: avoid;
    page-break-after: avoid;
  }
  .report-qa { font-size: 13px; margin: 0 0 8px; }
  .report-answer {
    font-size: 13px;
    background: #f8f9fa;
    padding: 12px;
    border-radius: 8px;
    margin: 0 0 12px;
    white-space: pre-wrap;
    break-inside: auto;
    page-break-inside: auto;
  }
  .report-h4 {
    color: #1a5fb4;
    margin: 14px 0 8px;
    font-size: 14px;
    break-after: avoid;
    page-break-after: avoid;
  }
  .report-h5 { margin: 10px 0 6px; font-size: 13px; }
  .report-score-line { font-size: 14px; margin: 0 0 8px; }
  .report-score { font-size: 22px; color: #1a5fb4; }
  .report-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    margin-top: 8px;
  }
  .report-table-head { background: #e8f0fb; }
  .report-table tr { break-inside: avoid; page-break-inside: avoid; }
  .report-articles > div,
  .report-citations > div {
    break-inside: avoid;
    page-break-inside: avoid;
  }
  .report-summary {
    font-size: 11px;
    background: #f0f4f8;
    padding: 8px;
    border-radius: 6px;
    white-space: pre-wrap;
    margin: 8px 0 0;
  }
  .report-disclaimer {
    font-size: 11px;
    color: #999;
    margin: 10px 0 0;
    text-align: center;
  }
  @page {
    size: A4;
    margin: 14mm 16mm;
  }
  @media print {
    html, body {
      width: auto;
      height: auto;
      overflow: visible;
    }
    .report-root {
      max-width: none;
      padding: 0;
    }
    .report-section {
      break-inside: auto;
      page-break-inside: auto;
    }
  }
`

/**
 * 组装整页报告并打开新窗口（成功后调用方退出导出模式）。
 * @returns 是否成功打开窗口（浏览器拦截弹窗时返回 false）
 */
export function exportTrustReport(session: Session, selectedIds: Set<string>): boolean {
  if (selectedIds.size === 0) return false
  const msgs = session.messages.filter((m) => selectedIds.has(m.id))
  const auth = useAuthStore()
  const now = new Date().toLocaleString('zh-CN')
  const sections = msgs.map((m) => buildReportSection(m, session)).join('')
  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>法信通 · 可信评估报告</title>
  <style>${REPORT_PRINT_CSS}</style>
</head>
<body>
  <div class="report-root">
    <header class="report-header">
      <h1>法信通 · 可信评估报告</h1>
      <div class="report-meta">
        对话：${escapeHtml(session.title)}<br/>
        导出人：${escapeHtml(auth.displayLabel)}<br/>
        导出时间：${escapeHtml(now)}<br/>
        共 ${msgs.length} 条法律问答
      </div>
    </header>
    ${sections}
  </div>
</body>
</html>`
  const w = window.open('', '_blank')
  if (!w) return false
  w.document.open()
  w.document.write(html)
  w.document.close()
  const triggerPrint = () => {
    w.focus()
    w.print()
  }
  if (w.document.readyState === 'complete') {
    setTimeout(triggerPrint, 350)
  } else {
    w.addEventListener('load', () => setTimeout(triggerPrint, 350))
  }
  return true
}
