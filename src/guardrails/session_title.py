"""Rule-based session title generation from the first user message."""
import re


_PREFIX_RE = re.compile(
    r"^(请问|我想问|咨询一下|麻烦|你好|您好|帮我|能不能|可以吗)[，,：:\s]*",
    re.IGNORECASE,
)

_LEGAL_TOPIC_HINTS = [
    (r"劳动合同|解除|辞退|裁员|试用期", "劳动合同咨询"),
    (r"工伤|伤残|工亡", "工伤赔偿咨询"),
    (r"离婚|抚养|财产分割", "婚姻家庭咨询"),
    (r"租赁|租房|押金", "房屋租赁咨询"),
    (r"交通事故|肇事|理赔", "交通事故咨询"),
    (r"消费者|退款|欺诈", "消费者权益咨询"),
    (r"仲裁|诉讼|起诉", "争议解决咨询"),
    (r"赔偿|违约金|违约", "违约赔偿咨询"),
]


def generate_session_title(query: str, max_len: int = 18) -> str:
    """Derive a short session name from the first user question."""
    text = (query or "").strip()
    if not text:
        return "新对话"

    text = _PREFIX_RE.sub("", text)

    for pat, label in _LEGAL_TOPIC_HINTS:
        if re.search(pat, text):
            return label

    for sep in ("？", "?", "。", "！", "!", "\n"):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
            if sep in ("？", "?"):
                text += "？"
            break

    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        return text[:max_len] + "…"
    return text or "法律咨询"
