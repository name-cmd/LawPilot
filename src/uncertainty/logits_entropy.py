"""
Token-level uncertainty via logits entropy.

For each generated token, compute Shannon entropy over the vocabulary distribution.
High-entropy tokens indicate positions where the model was uncertain about what to say.
Contiguous high-entropy spans are surfaced as risk segments.

⚠️ 实验性模块，未接入流水线。
API 模式下不可用：本模块需要本地模型的 token logits（依赖 QwenModel.model/.tokenizer），
LLM_PROVIDER="api" 时请勿使用；本地模式（LLM_PROVIDER=local）回归时仍可正常使用。
"""
from typing import List, Dict
import numpy as np
import torch


_HIGH_ENTROPY = 2.0   # bits
_MED_ENTROPY = 1.0    # bits


class LogitsEntropyAnalyzer:
    """
    Pass in the already-loaded HuggingFace model and tokenizer
    (both must be on the same device).
    """

    def __init__(self, model, tokenizer):
        self.model = model
        self.tokenizer = tokenizer

    def analyze(self, prompt: str, response: str) -> Dict:
        """
        Compute per-token entropy for `response` conditioned on `prompt`.

        Returns:
            tokens              – list of token strings
            token_entropies     – entropy (bits) per token
            avg_entropy         – mean entropy across the response
            max_entropy         – peak entropy
            high_entropy_segments – list of {text, avg_entropy, risk_level}
            uncertainty_score   – "低" / "中等" / "高" 不确定性
        """
        device = next(self.model.parameters()).device
        prompt_ids = self.tokenizer.encode(prompt, return_tensors="pt").to(device)
        resp_ids = self.tokenizer.encode(
            response, add_special_tokens=False, return_tensors="pt"
        ).to(device)

        full_ids = torch.cat([prompt_ids, resp_ids], dim=1)

        with torch.no_grad():
            logits = self.model(full_ids).logits  # (1, seq_len, vocab)

        # Logits for predicting each response token are at positions
        # [prompt_len-1 … prompt_len+resp_len-2] (teacher-forcing offset).
        p_len = prompt_ids.shape[1]
        r_len = resp_ids.shape[1]
        resp_logits = logits[0, p_len - 1 : p_len + r_len - 1, :]

        tokens, entropies = [], []
        for i in range(r_len):
            probs = torch.softmax(resp_logits[i], dim=-1)
            entropy = float(-torch.sum(probs * torch.log2(probs + 1e-12)).item())
            entropies.append(entropy)
            tokens.append(self.tokenizer.decode([resp_ids[0, i].item()]))

        avg_entropy = float(np.mean(entropies))
        segments = self._find_segments(tokens, entropies)

        return {
            "tokens": tokens,
            "token_entropies": [round(e, 4) for e in entropies],
            "avg_entropy": round(avg_entropy, 4),
            "max_entropy": round(float(np.max(entropies)), 4),
            "high_entropy_segments": segments,
            "uncertainty_score": _level(avg_entropy),
        }

    @staticmethod
    def _find_segments(tokens: List[str], entropies: List[float]) -> List[Dict]:
        segments = []
        i = 0
        while i < len(tokens):
            if entropies[i] >= _HIGH_ENTROPY:
                start = i
                while i < len(tokens) and entropies[i] >= _MED_ENTROPY:
                    i += 1
                text = "".join(tokens[start:i]).strip()
                if text:
                    avg = float(np.mean(entropies[start:i]))
                    segments.append({
                        "text": text,
                        "avg_entropy": round(avg, 4),
                        "risk_level": "高" if avg >= _HIGH_ENTROPY else "中",
                    })
            else:
                i += 1
        return segments


def _level(avg: float) -> str:
    if avg < _MED_ENTROPY:
        return "低不确定性"
    if avg < _HIGH_ENTROPY:
        return "中等不确定性"
    return "高不确定性"
