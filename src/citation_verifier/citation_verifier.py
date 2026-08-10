"""
Three-level citation verification pipeline.

Level 1 — Regex: does the cited article number exist in the knowledge base?
Level 2 — Content match: does the model's description match the actual text?
Level 3 — Implicit claims: do uncited legal assertions have a supporting article?
"""
import json
from typing import List, Dict, Optional

from langchain_core.documents import Document

from .extractor import CitationExtractor
from .content_verifier import ContentVerifier
from .implicit_verifier import ImplicitClaimVerifier
from src.citation_verifier.document_quotes import DocumentQuoteVerifier
from src.knowledge_base.vector_store import LawVectorStore
from src.knowledge_base.embedder import LawEmbedder
from src.knowledge_base.law_name_resolver import resolve_law_name
from src.knowledge_base.law_validity import LawValidityService
from src.config import Config


class CitationVerifier:
    def __init__(
        self,
        vector_store: LawVectorStore,
        embedder: LawEmbedder,
        enable_nli: bool = True,
        nli_model_name: str = None,
        validity_service: LawValidityService = None,
    ):
        self.validity = validity_service or LawValidityService()
        self.extractor = CitationExtractor()
        self.content_verifier = ContentVerifier(
            vector_store, embedder, validity_service=self.validity
        )
        self.implicit_verifier = (
            ImplicitClaimVerifier(vector_store, nli_model_name) if enable_nli else None
        )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def verify(
        self,
        llm_response: str,
        retrieved_docs: Optional[List[Document]] = None,
        user_documents: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Verify an LLM response and return a structured report.

        retrieved_docs: optional RAG hits — used to check citations align with retrieval.
        user_documents: 用户上传文档（合同等）——回答引用的文档原文须与文档逐字一致。
        """
        rag_keys = self._rag_article_keys(retrieved_docs)

        citations = self.extractor.extract(llm_response)
        citation_results = []
        for c in citations:
            res = self.content_verifier.verify(c, full_response=llm_response)
            article_for_rag = c.article_num or res.get("resolved_article_num") or ""
            resolved = res.get("resolved_law_name") or resolve_law_name(c.law_name)
            in_rag = (resolved, article_for_rag) in rag_keys if rag_keys else None
            severity = res.get("severity") or self._severity(c, res)

            display_article = c.article_num or res.get("resolved_article_num") or ""
            cite_label = c.raw_text
            if c.is_law_level and display_article:
                cite_label = (
                    f"{c.raw_text}（语义对应{display_article}）"
                )
            citation_results.append({
                "text": cite_label,
                "law_name": c.law_name,
                "resolved_law_name": resolved,
                "article_num": display_article,
                "exists": res["exists"],
                "rouge_l": res.get("rouge_l"),
                "cosine_similarity": res.get("cosine_similarity"),
                "content_match_score": res.get("content_match_score"),
                "quoted_text": res.get("quoted_text") or res.get("arguing_sentence") or c.quoted_text,
                "arguing_sentence": res.get("arguing_sentence"),
                "reference_excerpt": res.get("reference_excerpt"),
                "semantic_match": res.get("semantic_match", False),
                "wrong_article_mismatch": res.get("wrong_article_mismatch", False),
                "suggested_article_num": res.get("suggested_article_num"),
                "irrelevant_mention": res.get("irrelevant_mention", False),
                "auto_aligned": res.get("auto_aligned", False),
                "actual_content": res.get("actual_content"),
                "in_retrieved_context": in_rag,
                "verdict": res["verdict"],
                "validity": res.get("validity"),
                "severity": severity,
                "highlight_span": self._highlight_span(llm_response, c.raw_text),
            })

        implicit_results = []
        if self.implicit_verifier:
            claims = self.implicit_verifier.extract_claims(llm_response)
            for claim in claims[:5]:
                implicit_results.append(self.implicit_verifier.verify_claim(claim))

        overall = self._overall_score(citation_results, implicit_results)
        validity_warnings = self.validity.collect_warnings_from_citations(
            citation_results
        )
        document_quote_checks = None
        if user_documents:
            document_quote_checks = DocumentQuoteVerifier().verify(
                llm_response, user_documents
            )["document_quote_checks"]

        return {
            "extracted_citations": citation_results,
            "implicit_claims": implicit_results,
            "overall_citation_score": round(overall, 4),
            "summary": self._summary(
                citation_results, implicit_results, overall, rag_keys
            ),
            "validity_warnings": validity_warnings,
            "document_quote_checks": document_quote_checks,
        }

    def verify_and_print(self, llm_response: str) -> None:
        print(json.dumps(self.verify(llm_response), ensure_ascii=False, indent=2))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _highlight_span(text: str, raw_citation: str) -> Optional[Dict]:
        if not raw_citation or not text:
            return None
        idx = text.find(raw_citation)
        if idx < 0:
            return None
        return {"start": idx, "end": idx + len(raw_citation)}

    @staticmethod
    def _severity(citation, res: Dict) -> str:
        validity = res.get("validity") or {}
        if validity and not validity.get("effective", True):
            return "error"
        if not res.get("exists") or res.get("wrong_article_mismatch"):
            return "error"
        if res.get("irrelevant_mention"):
            return "warning"
        score = res.get("content_match_score") or 0.0
        if score >= Config.CONTENT_MATCH_THRESHOLD:
            return "ok"
        if score >= 0.4:
            return "warning"
        return "error"

    @staticmethod
    def _rag_article_keys(docs: Optional[List[Document]]) -> set:
        if not docs:
            return set()
        keys = set()
        for d in docs:
            law = d.metadata.get("law_name", "")
            num = d.metadata.get("article_num", "")
            if law and num:
                keys.add((resolve_law_name(law), num))
        return keys

    @staticmethod
    def _overall_score(citations: List[Dict], implicits: List[Dict]) -> float:
        scores = []
        for r in citations:
            validity = r.get("validity") or {}
            if validity and not validity.get("effective", True):
                scores.append(0.0)
                continue
            if r.get("wrong_article_mismatch") or r.get("irrelevant_mention"):
                scores.append(0.0)
            else:
                scores.append(
                    r.get("content_match_score") or (1.0 if r["exists"] else 0.0)
                )
        for r in implicits:
            scores.append(r.get("support_score", 0.5))
        return sum(scores) / len(scores) if scores else 1.0

    @staticmethod
    def _summary(
        citations: List[Dict],
        implicits: List[Dict],
        score: float,
        rag_keys: set,
    ) -> str:
        total = len(citations)
        valid = sum(1 for r in citations if r["exists"])
        repealed = sum(
            1 for r in citations
            if (r.get("validity") or {}).get("effective") is False
        )
        threshold = Config.CONTENT_MATCH_THRESHOLD
        accurate = sum(
            1 for r in citations
            if (r.get("content_match_score") or 0) >= threshold
            and not r.get("wrong_article_mismatch")
            and not r.get("irrelevant_mention")
            and (r.get("validity") or {}).get("effective", True)
        )
        mismatched = sum(1 for r in citations if r.get("wrong_article_mismatch"))
        irrelevant = sum(1 for r in citations if r.get("irrelevant_mention"))
        missing_quote = sum(
            1 for r in citations
            if r["exists"]
            and not r.get("quoted_text")
            and not r.get("irrelevant_mention")
            and "未提供条文原文摘录" in (r.get("verdict") or "")
        )

        lines = [
            f"共检测到 {total} 处显式法条引用",
            f"  ✓ 法条存在：{valid}/{total}",
            f"  ✓ 内容准确（≥{threshold}）：{accurate}/{total}",
        ]
        if repealed:
            lines.append(f"  ✗ 引用已废止法律：{repealed}/{total}")
        if mismatched:
            lines.append(f"  ✗ 条号与内容不符：{mismatched}/{total}")
        if irrelevant:
            lines.append(f"  ✗ 无关条文引用：{irrelevant}/{total}")
        if missing_quote:
            lines.append(f"  ⚠ 缺少可核验引文：{missing_quote}/{total}")
        if rag_keys:
            in_rag = sum(1 for r in citations if r.get("in_retrieved_context"))
            lines.append(f"  ✓ 引用落在本次检索结果内：{in_rag}/{total}")
        if implicits:
            supported = sum(1 for r in implicits if r.get("supported"))
            lines.append(f"  ✓ 隐性论断有法律支撑：{supported}/{len(implicits)}")
        lines.append(f"综合引用准确率：{score:.1%}")
        return "\n".join(lines)
