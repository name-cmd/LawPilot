"""Rule-based intent routing: legal QA vs greeting vs general non-legal."""
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

_GREETING_RE = re.compile(
    r"^(你好|您好|嗨|哈喽|hello|hi|在吗|早上好|下午好|晚上好|谢谢|感谢|再见|拜拜)"
    r"[\?？!！。…~\s]*$",
    re.IGNORECASE,
)

_LEGAL_KEYWORDS = (
    "法律", "法条", "合同", "劳动", "仲裁", "诉讼", "起诉", "赔偿", "违约",
    "辞退", "解除", "开除", "解雇", "裁员", "工伤", "社保", "工资", "欠薪",
    "租赁", "租房", "离婚", "抚养", "继承", "侵权", "消费者", "退款",
    "交通事故", "肇事", "维权", "违法", "犯罪", "刑法", "民法", "宪法",
    "法院", "检察院", "律师", "调解", "判决", "裁定", "执行", "拘留",
    "罚款", "责任", "义务", "权利", "证件", "身份证", "押金", "违约金",
)

_NON_LEGAL_RE = re.compile(
    r"(天气|气温|下雨|写诗|作文|翻译|编程|代码|股票|彩票|美食|菜谱|"
    r"旅游攻略|游戏|电影推荐|笑话|段子|数学题|物理题|化学题|"
    r"今天几号|现在几点)",
    re.IGNORECASE,
)


@dataclass
class IntentResult:
    intent: str  # legal_qa | greeting | general_non_legal
    confidence: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "reason": self.reason,
        }


def _has_legal_keywords(text: str) -> bool:
    return any(kw in text for kw in _LEGAL_KEYWORDS)


def _is_greeting(text: str) -> bool:
    return bool(_GREETING_RE.match(text.strip()))


def _is_non_legal(text: str) -> bool:
    return bool(_NON_LEGAL_RE.search(text))


def _history_has_legal_context(history: Optional[List[Dict[str, str]]]) -> bool:
    if not history:
        return False
    recent = " ".join(
        m.get("content", "")
        for m in history[-4:]
        if m.get("role") == "user"
    )
    return _has_legal_keywords(recent)


def classify_intent(
    query: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> IntentResult:
    """Classify user query before RAG / generation."""
    text = (query or "").strip()
    if not text:
        return IntentResult("general_non_legal", 1.0, "空输入")

    if _is_greeting(text):
        return IntentResult("greeting", 0.95, "寒暄问候")

    if _has_legal_keywords(text):
        return IntentResult("legal_qa", 0.92, "包含法律相关关键词")

    if _is_non_legal(text):
        return IntentResult("general_non_legal", 0.88, "非法律领域问题")

    if _history_has_legal_context(history):
        return IntentResult("legal_qa", 0.75, "法律对话上下文延续")

    if len(text) <= 8:
        return IntentResult("greeting", 0.7, "简短输入，按寒暄处理")

    return IntentResult("general_non_legal", 0.65, "未识别法律意图，按通用回复处理")
