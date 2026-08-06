"""
Pre-submit input guard: misuse refusal, PII scan, and critical PII masking.

Inspired by TrustLLM safety/misuse evaluation and common guardrail patterns
(RtA refusal detection, PII redaction before LLM inference).
"""
from dataclasses import dataclass, field
from typing import List, Optional

from src.trust_eval.dimensions.rules import (
    detect_input_pii,
    get_misuse_refusal_message,
    is_misuse_query,
    mask_critical_pii,
)


@dataclass
class InputGuardResult:
    allowed: bool
    refused: bool = False
    refusal_reason: Optional[str] = None
    refusal_message: Optional[str] = None
    sanitized_query: str = ""
    has_pii: bool = False
    pii_types: List[str] = field(default_factory=list)
    critical_pii_masked: bool = False
    needs_privacy_confirm: bool = False
    privacy_warning: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "refused": self.refused,
            "refusal_reason": self.refusal_reason,
            "refusal_message": self.refusal_message,
            "sanitized_query": self.sanitized_query,
            "has_pii": self.has_pii,
            "pii_types": self.pii_types,
            "critical_pii_masked": self.critical_pii_masked,
            "needs_privacy_confirm": self.needs_privacy_confirm,
            "privacy_warning": self.privacy_warning,
        }


class InputGuard:
    """Validate and sanitize user queries before they reach the LLM pipeline."""

    def check(
        self,
        query: str,
        privacy_confirmed: bool = False,
    ) -> InputGuardResult:
        text = (query or "").strip()
        if not text:
            return InputGuardResult(
                allowed=False,
                sanitized_query="",
                privacy_warning="请输入法律问题",
            )

        if is_misuse_query(text):
            return InputGuardResult(
                allowed=False,
                refused=True,
                refusal_reason="misuse",
                refusal_message=get_misuse_refusal_message(text),
                sanitized_query=text,
            )

        sanitized, masked_critical = mask_critical_pii(text)
        pii_scan = detect_input_pii(sanitized)
        all_types = pii_scan["critical"] + pii_scan["moderate"]
        has_pii = bool(all_types)

        needs_confirm = bool(pii_scan["moderate"]) and not privacy_confirmed
        warning = None
        if needs_confirm:
            types_str = "、".join(pii_scan["moderate"])
            warning = (
                f"检测到输入中包含可能涉及隐私的信息（{types_str}）。"
                "继续提问将把该内容用于法律咨询分析，请确认是否仍要发送。"
            )

        return InputGuardResult(
            allowed=not needs_confirm,
            sanitized_query=sanitized,
            has_pii=has_pii,
            pii_types=all_types,
            critical_pii_masked=masked_critical,
            needs_privacy_confirm=needs_confirm,
            privacy_warning=warning,
        )
