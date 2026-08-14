"""
Self-consistency based uncertainty quantification (SelfCheckGPT variant).

Strategy: generate N responses at different temperatures → embed all →
measure pairwise cosine similarity → low avg similarity = high uncertainty.
"""
from typing import Dict, List, Optional
import numpy as np
from src.config import Config


class SelfConsistencyChecker:
    """
    Requires a model that exposes a .generate(query, temperature=...) method
    and an embedder with .embed_query(text) -> List[float].
    """

    def __init__(self, model, embedder):
        self.model = model
        self.embedder = embedder

    def check(
        self,
        query: str,
        system_prompt: str = "",
        n_samples: int = None,
        temperatures: List[float] = None,
        context_docs: List[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        model_id: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> Dict:
        """
        Sample n_samples responses and return a consistency/uncertainty report.

        Returns:
            responses           – all sampled texts
            similarity_matrix   – N×N pairwise cosine similarities
            avg_consistency     – scalar in [0, 1]
            uncertainty_level   – "低" / "中等" / "高" 不确定性
            best_response       – most central (highest mean similarity) response
            uncertainty_warning – True when avg_consistency < threshold
        """
        n_samples = n_samples or Config.N_SAMPLES
        temperatures = temperatures or Config.TEMPERATURE_RANGE[:n_samples]

        responses = [
            self.model.generate(
                query,
                system_prompt=system_prompt or None,
                temperature=t,
                context_docs=context_docs,
                history=history,
                model_id=model_id,  # 自一致性采样沿用主回答所用模型
                api_key=api_key,    # 自一致性采样沿用主回答所用 API Key
            )
            for t in temperatures
        ]

        sim_matrix = self._similarity_matrix(responses)
        n = len(responses)
        off_diag = [sim_matrix[i][j] for i in range(n) for j in range(n) if i != j]
        avg = float(np.mean(off_diag))

        # Pick the response closest to the centroid
        row_means = [np.mean([sim_matrix[i][j] for j in range(n) if j != i]) for i in range(n)]
        best_idx = int(np.argmax(row_means))

        return {
            "responses": responses,
            "similarity_matrix": sim_matrix.tolist(),
            "avg_consistency": round(avg, 4),
            "uncertainty_level": self._level(avg),
            "best_response": responses[best_idx],
            "best_response_idx": best_idx,
            "uncertainty_warning": avg < Config.CONSISTENCY_THRESHOLD,
        }

    # ------------------------------------------------------------------

    def _similarity_matrix(self, texts: List[str]) -> np.ndarray:
        embeddings = [np.array(self.embedder.embed_query(t)) for t in texts]
        n = len(embeddings)
        mat = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                denom = np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j]) + 1e-8
                sim = float(np.dot(embeddings[i], embeddings[j]) / denom)
                mat[i][j] = sim
                mat[j][i] = sim
        return mat

    @staticmethod
    def _level(avg: float) -> str:
        if avg >= 0.85:
            return "低不确定性"
        if avg >= 0.6:
            return "中等不确定性"
        return "高不确定性"
