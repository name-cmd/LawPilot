"""
Level 2 — Content verifier.
Compares the model's *arguing sentence* (论述句) with the most relevant
法条原文 or 款/项, using semantic similarity as the primary signal.
"""
import re
from typing import Dict, List, Optional, Tuple
import numpy as np
from rouge_score import rouge_scorer
from .extractor import Citation
from .article_text import (
    article_body,
    best_matching_clause,
    extract_clause_body,
)
from .sentence_utils import sentence_at
from src.knowledge_base.vector_store import LawVectorStore
from src.knowledge_base.embedder import LawEmbedder
from src.knowledge_base.law_name_resolver import resolve_law_name
from src.knowledge_base.law_validity import LawValidityService
from src.config import Config


class ContentVerifier:
    def __init__(
        self,
        vector_store: LawVectorStore,
        embedder: LawEmbedder,
        validity_service: LawValidityService = None,
    ):
        self.store = vector_store
        self.embedder = embedder
        self.validity = validity_service or LawValidityService()
        self._rouge = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=False)

    def _check_validity(self, law_name: str, article_num: str, doc_metadata=None) -> Dict:
        result = self.validity.check_citation(
            law_name, article_num, doc_metadata=doc_metadata
        )
        return result.to_dict()

    def verify(self, citation: Citation, full_response: str = "") -> Dict:
        registry_validity = self._check_validity(
            citation.law_name,
            citation.article_num or citation.resolved_article_num,
        )
        if not registry_validity.get("effective") and not citation.is_law_level:
            return self._repealed_result(registry_validity)

        arguing = self._arguing_sentence(citation, full_response)
        if citation.is_irrelevant_mention:
            doc = self._get_doc(citation)
            return self._irrelevant_result(citation, doc, arguing, registry_validity)

        if citation.is_law_level:
            return self._verify_law_level(citation, arguing, registry_validity)

        return self._verify_article_citation(
            citation, arguing, full_response, registry_validity
        )

    def _verify_law_level(
        self, citation: Citation, arguing: str, registry_validity: Dict
    ) -> Dict:
        doc, combined_article_score = self._resolve_best_article(
            citation.law_name, arguing
        )
        if doc is None:
            return {
                "exists": False,
                "rouge_l": 0.0,
                "cosine_similarity": 0.0,
                "content_match_score": 0.0,
                "actual_content": None,
                "arguing_sentence": arguing,
                "quoted_text": arguing,
                "reference_excerpt": None,
                "verdict": "❌ 未在知识库中找到相关法律条文",
                "validity": registry_validity,
                "severity": "error",
                "semantic_match": True,
            }

        article_num = doc.metadata.get("article_num", "")
        citation.resolved_article_num = article_num
        body = article_body(doc.page_content)
        reference = best_matching_clause(body, arguing, self.embedder.embed_query)
        rouge_l, cosine, combined = self._semantic_match_score(arguing, reference)

        doc_validity = self._check_validity(
            citation.law_name, article_num, doc_metadata=doc.metadata
        )
        if not doc_validity.get("effective"):
            return self._repealed_result(doc_validity, doc=doc, arguing=arguing)

        result = {
            "exists": True,
            "resolved_law_name": doc.metadata.get("law_name"),
            "resolved_article_num": article_num,
            "rouge_l": round(rouge_l, 4),
            "cosine_similarity": round(cosine, 4),
            "content_match_score": round(combined, 4),
            "actual_content": doc.page_content,
            "arguing_sentence": arguing,
            "quoted_text": arguing,
            "reference_excerpt": reference,
            "auto_aligned": True,
            "semantic_match": True,
            "verdict": self._verdict(combined),
        }
        if combined >= Config.CONTENT_MATCH_THRESHOLD:
            result["verdict"] = (
                f"✅ 语义吻合（论述与《{doc.metadata.get('law_name')}》"
                f"{article_num}一致）"
            )
        result["validity"] = doc_validity
        result["severity"] = self._severity_from_result(result)
        return result

    def _verify_article_citation(
        self,
        citation: Citation,
        arguing: str,
        full_response: str,
        registry_validity: Dict,
    ) -> Dict:
        if not registry_validity.get("effective"):
            return self._repealed_result(registry_validity)

        doc = self._get_doc(citation)
        if doc is None:
            return {
                "exists": False,
                "rouge_l": 0.0,
                "cosine_similarity": 0.0,
                "content_match_score": 0.0,
                "actual_content": None,
                "arguing_sentence": arguing,
                "quoted_text": arguing,
                "verdict": "❌ 法条不存在",
                "validity": registry_validity,
                "severity": "error",
                "semantic_match": True,
            }

        doc_validity = self._check_validity(
            citation.law_name,
            citation.article_num,
            doc_metadata=doc.metadata,
        )
        if not doc_validity.get("effective"):
            return self._repealed_result(
                doc_validity, doc=doc, arguing=arguing
            )

        actual_body = article_body(doc.page_content)
        reference = self._reference_text(citation, actual_body, arguing)

        quote = citation.quoted_text
        if quote and len(quote) >= 8:
            rouge_l, cosine, combined = self._semantic_match_score(quote, reference)
            hypothesis_label = quote
            auto_aligned = False
        else:
            rouge_l, cosine, combined = self._semantic_match_score(arguing, reference)
            hypothesis_label = arguing
            auto_aligned = True

        result = {
            "exists": True,
            "resolved_law_name": doc.metadata.get("law_name"),
            "rouge_l": round(rouge_l, 4),
            "cosine_similarity": round(cosine, 4),
            "content_match_score": round(combined, 4),
            "actual_content": doc.page_content,
            "arguing_sentence": arguing,
            "quoted_text": hypothesis_label,
            "reference_excerpt": reference,
            "auto_aligned": auto_aligned,
            "semantic_match": True,
            "verdict": self._verdict(combined),
        }
        if auto_aligned and combined >= Config.CONTENT_MATCH_THRESHOLD:
            result["verdict"] = "✅ 语义吻合（论述与法条内容一致）"

        mismatch = self._detect_wrong_article(
            citation.law_name,
            citation.article_num,
            arguing,
            combined,
        )
        if mismatch:
            result.update(mismatch)
            result["verdict"] = (
                f"❌ 条号与内容不符（论述更接近《{mismatch['suggested_law_name']}》"
                f"{mismatch['suggested_article_num']}）"
            )

        result["validity"] = doc_validity
        result["severity"] = self._severity_from_result(result)
        return result

    def _reference_text(
        self, citation: Citation, actual_body: str, arguing: str
    ) -> str:
        if citation.clause_item is not None or citation.clause_kuan is not None:
            clause = extract_clause_body(
                actual_body,
                item=citation.clause_item,
                kuan=citation.clause_kuan,
            )
            if clause != actual_body:
                return clause

        if citation.clause_item is None and citation.clause_kuan is None:
            enumerated = best_matching_clause(
                actual_body, arguing, self.embedder.embed_query
            )
            if enumerated != actual_body and len(enumerated) < len(actual_body) * 0.85:
                return enumerated
        return actual_body

    def _resolve_best_article(
        self, law_name: str, arguing: str
    ) -> Tuple[Optional[object], float]:
        canonical = resolve_law_name(law_name)
        hits = self.store.similarity_search(arguing, k=20)
        best_doc = None
        best_score = -1.0
        for doc in hits:
            meta = doc.metadata or {}
            hit_law = meta.get("law_name", "")
            if hit_law != canonical and resolve_law_name(hit_law) != canonical:
                continue
            body = article_body(doc.page_content)
            _, _, combined = self._semantic_match_score(arguing, body)
            if combined > best_score:
                best_score = combined
                best_doc = doc
        return best_doc, best_score

    def _get_doc(self, citation: Citation):
        return self.store.get_article(citation.law_name, citation.article_num)

    @staticmethod
    def _arguing_sentence(citation: Citation, full_response: str) -> str:
        if citation.arguing_sentence:
            return citation.arguing_sentence.strip()
        if full_response and citation.position >= 0:
            return sentence_at(full_response, citation.position)
        return (citation.context or "").strip()

    def _semantic_match_score(
        self, claim: str, reference: str
    ) -> Tuple[float, float, float]:
        claim = claim.strip()
        reference = reference.strip()
        if not claim or not reference:
            return 0.0, 0.0, 0.0

        rouge_l = self._rouge_l(claim, reference)
        cosine = self._cosine(claim, reference)
        combined = 0.25 * rouge_l + 0.75 * cosine

        if self._normalized_contains(claim, reference):
            combined = max(combined, 0.92)
        elif cosine >= 0.84:
            combined = max(combined, 0.88)
        elif cosine >= 0.76:
            combined = max(combined, 0.78)

        return rouge_l, cosine, combined

    def _repealed_result(
        self,
        validity: Dict,
        doc=None,
        arguing: str = "",
    ) -> Dict:
        return {
            "exists": bool(doc),
            "rouge_l": 0.0,
            "cosine_similarity": 0.0,
            "content_match_score": 0.0,
            "actual_content": doc.page_content if doc else None,
            "arguing_sentence": arguing,
            "quoted_text": arguing,
            "verdict": f"❌ 已废止 — {validity.get('warning_message', '')}",
            "validity": validity,
            "severity": "error",
            "semantic_match": True,
        }

    def _irrelevant_result(self, citation, doc, arguing, validity) -> Dict:
        return {
            "exists": True,
            "resolved_law_name": doc.metadata.get("law_name") if doc else None,
            "rouge_l": 0.0,
            "cosine_similarity": 0.0,
            "content_match_score": 0.0,
            "actual_content": doc.page_content if doc else None,
            "arguing_sentence": arguing,
            "quoted_text": arguing,
            "irrelevant_mention": True,
            "verdict": "⚠️ 无关条文引用（否定式提及，与问题无关）",
            "validity": validity,
            "severity": "warning",
            "semantic_match": True,
        }

    @staticmethod
    def _severity_from_result(result: Dict) -> str:
        if not result.get("exists") or result.get("wrong_article_mismatch"):
            return "error"
        if result.get("irrelevant_mention"):
            return "warning"
        score = result.get("content_match_score") or 0.0
        if score >= Config.CONTENT_MATCH_THRESHOLD:
            return "ok"
        if score >= 0.4:
            return "warning"
        return "error"

    def _detect_wrong_article(
        self,
        law_name: str,
        article_num: str,
        hypothesis: str,
        score_for_cited: float,
    ) -> Optional[Dict]:
        if score_for_cited >= Config.CONTENT_MATCH_THRESHOLD:
            return None
        if len(hypothesis.strip()) < 12:
            return None

        hits = self.store.similarity_search(hypothesis, k=12)
        canonical = resolve_law_name(law_name)
        best: Optional[Tuple[float, str, str]] = None

        for doc in hits:
            meta = doc.metadata
            hit_law = meta.get("law_name", "")
            hit_num = meta.get("article_num", "")
            if hit_law != canonical and resolve_law_name(hit_law) != canonical:
                continue
            if hit_num == article_num:
                continue

            body = article_body(doc.page_content)
            _, _, combined = self._semantic_match_score(hypothesis, body)
            suggest_threshold = Config.MISMATCH_SUGGEST_THRESHOLD
            if combined >= suggest_threshold and (
                best is None or combined > best[0]
            ):
                best = (combined, hit_law, hit_num)

        if best is None:
            return None
        if best[0] <= score_for_cited + 0.08:
            return None

        return {
            "wrong_article_mismatch": True,
            "suggested_law_name": best[1],
            "suggested_article_num": best[2],
            "suggested_match_score": round(best[0], 4),
        }

    def _rouge_l(self, hyp: str, ref: str) -> float:
        try:
            return self._rouge.score(ref, hyp)["rougeL"].fmeasure
        except Exception:
            return 0.0

    def _cosine(self, t1: str, t2: str) -> float:
        try:
            e1 = np.array(self.embedder.embed_query(t1))
            e2 = np.array(self.embedder.embed_query(t2))
            denom = np.linalg.norm(e1) * np.linalg.norm(e2) + 1e-8
            return float(np.dot(e1, e2) / denom)
        except Exception:
            return 0.0

    @staticmethod
    def _normalized_contains(needle: str, haystack: str) -> bool:
        n = re.sub(r"\s+", "", needle)
        h = re.sub(r"\s+", "", haystack)
        if len(n) < 10:
            return False
        return n in h

    @staticmethod
    def _verdict(score: float) -> str:
        if score >= Config.CONTENT_MATCH_THRESHOLD:
            return "✅ 内容吻合"
        if score >= 0.4:
            return "⚠️ 内容部分符合"
        return "❌ 内容不符"
