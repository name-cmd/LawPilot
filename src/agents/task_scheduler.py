"""任务调度器：把 legal_qa 意图细分为任务类型，分派到专业管线（主管-专家）。

设计要点：
- 确定性规则分类（不用大模型）：快、稳、便宜、可解释；
- 回退安全：规则不命中一律落回 legal_qa（最坏情况 = 现状，不退化）；
- 时效查询的法律名动态取自 law_registry.json（不硬编码废止法律清单）。
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from src.config import Config
from src.pipeline.intent_router import IntentResult

# 合同审查提问信号（与「是否携带文档」组合判断）
_CONTRACT_REVIEW_RE = re.compile(r"帮我审|审一下|帮忙审|审查|把关|漏洞|这份合同|这份协议|(合同|协议).*(风险|条款|问题|审查)")
# 无文档时的强个人审查意图（此时输出引导上传）
_CONTRACT_REVIEW_NO_DOC_RE = re.compile(r"帮我审|审一下|帮忙审|帮我看看.*(合同|协议)|(合同|协议).*(审查|风险|把关)")
# 时效查询提问信号
_VALIDITY_QUERY_RE = re.compile(r"还有效|有效吗|是否有效|废止|作废|失效|还有没有效|现在.*适用|替代|新法|生效")


@dataclass
class TaskDecision:
    task_type: str   # legal_qa | contract_review | validity_check
    confidence: float
    reason: str
    law_name: Optional[str] = None  # validity_check 命中的注册表法律名

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type,
            "confidence": self.confidence,
            "reason": self.reason,
            "law_name": self.law_name,
        }


def _load_registry_names(registry_path: str) -> List[str]:
    """读取注册表键（废止/修订法律名）；文件缺失或损坏返回空表（调度器照常工作）。"""
    p = Path(registry_path)
    if not p.exists():
        return []
    try:
        return list(json.loads(p.read_text(encoding="utf-8")).keys())
    except Exception:
        return []


def classify_task(
    query: str,
    intent: IntentResult,
    user_documents: Optional[List[Dict]] = None,
    registry_path: Optional[str] = None,
) -> TaskDecision:
    """任务分类：仅在 intent == legal_qa 时细化；其他意图不做任务细分。"""
    if intent.intent != "legal_qa":
        return TaskDecision("legal_qa", intent.confidence, "非法律问答意图，不做任务细化")

    text = (query or "").strip()
    docs = user_documents or []

    # 时效查询：问题点名废止法律 + 时效措辞
    names = _load_registry_names(registry_path or str(Config.LAW_REGISTRY_PATH))
    if names and _VALIDITY_QUERY_RE.search(text):
        mentioned = [n for n in names if n in text]
        if mentioned:
            return TaskDecision(
                "validity_check", 0.9,
                f"时效查询：提及废止法律《{mentioned[0]}》",
                law_name=mentioned[0],
            )

    # 合同审查：携带文档 + 审查信号
    if docs and _CONTRACT_REVIEW_RE.search(text):
        return TaskDecision("contract_review", 0.85, "携带文档且提问含合同审查信号")

    # 合同审查（无文档）：强个人审查意图 → 输出引导上传
    if _CONTRACT_REVIEW_NO_DOC_RE.search(text):
        return TaskDecision("contract_review", 0.8, "合同审查意图（无文档，输出引导）")

    return TaskDecision("legal_qa", 0.6, "默认法律问答")
