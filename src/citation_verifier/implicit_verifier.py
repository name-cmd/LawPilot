"""
Level 3 — Implicit claim verifier.
Detects legal assertions made without explicit citations and checks whether
the knowledge base contains supporting law via retrieval + NLI entailment.
"""
import re
from typing import List, Dict, Optional
import torch
from src.knowledge_base.vector_store import LawVectorStore
from src.config import Config

# Sentences containing these patterns are candidate legal claims.
_CLAIM_PATTERNS = [
    r'根据(?:法律|法规|相关规定)',
    r'依照(?:法律|法规|规定)',
    r'依法(?:应当|不得|有权|无权)',
    r'法律(?:规定|明确|要求)',
    r'应当[一-鿿]{2,20}',
    r'不得[一-鿿]{2,20}',
    r'有权[一-鿿]{2,20}',
    r'须[一-鿿]{2,10}',
]
_CLAIM_RE = re.compile('|'.join(_CLAIM_PATTERNS))
_SENT_SPLIT = re.compile(r'[。！？；\n]')


class ImplicitClaimVerifier:
    def __init__(self, vector_store: LawVectorStore, nli_model_name: str = None):
        self.store = vector_store
        self.nli_model_name = nli_model_name or Config.NLI_MODEL_NAME
        self._pipeline = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_claims(self, text: str) -> List[str]:
        sentences = [s.strip() for s in _SENT_SPLIT.split(text) if len(s.strip()) > 8]
        return [s for s in sentences if _CLAIM_RE.search(s)]

    def verify_claim(self, claim: str, top_k: int = 3) -> Dict:
        results = self.store.similarity_search_with_score(claim, k=top_k)
        if not results:
            return self._no_support(claim)

        best_doc, distance = results[0]
        # ChromaDB returns L2 distance; convert to rough similarity score
        retrieval_sim = max(0.0, 1.0 - distance)

        nli_score = self._entailment_score(best_doc.page_content, claim)
        support_score = 0.5 * retrieval_sim + 0.5 * nli_score

        law_ref = (
            f"《{best_doc.metadata.get('law_name', '')}》"
            f"{best_doc.metadata.get('article_num', '')}"
        )
        supported = support_score >= Config.NLI_THRESHOLD

        return {
            "claim": claim,
            "supporting_law": law_ref,
            "supporting_content": best_doc.page_content[:200],
            "retrieval_score": round(retrieval_sim, 4),
            "nli_score": round(nli_score, 4),
            "support_score": round(support_score, 4),
            "supported": supported,
            "verdict": "✅ 有法律支撑" if supported else "❌ 缺乏法律依据",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_nli(self):
        if self._pipeline is None:
            from transformers import pipeline
            self._pipeline = pipeline(
                "text-classification",
                model=self.nli_model_name,
                device=0 if torch.cuda.is_available() else -1,
            )
        return self._pipeline

    def _entailment_score(self, premise: str, hypothesis: str) -> float:
        try:
            nli = self._load_nli()
            text = f"{premise[:256]}[SEP]{hypothesis[:128]}"
            out = nli(text, truncation=True, max_length=512)[0]
            label = out['label'].lower()
            score = out['score']
            if 'entail' in label:
                return float(score)
            if 'contradict' in label:
                return 1.0 - float(score)
            return 0.5
        except Exception:
            return 0.5

    @staticmethod
    def _no_support(claim: str) -> Dict:
        return {
            "claim": claim,
            "supporting_law": None,
            "supporting_content": None,
            "retrieval_score": 0.0,
            "nli_score": 0.0,
            "support_score": 0.0,
            "supported": False,
            "verdict": "❌ 未找到支撑法条",
        }
