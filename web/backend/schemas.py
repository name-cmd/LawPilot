"""Pydantic schemas for LawTrust API."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class UserDocumentAttachment(BaseModel):
    filename: str = Field(..., min_length=1, max_length=256)
    text: str = Field(..., min_length=1, max_length=50000)
    format: Optional[str] = None
    char_count: Optional[int] = None


class DocumentExtractResponse(BaseModel):
    filename: str
    text: str
    format: str
    char_count: int
    page_count: int = 0
    extraction_methods: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)


class CheckInputRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    privacy_confirmed: bool = False


class CheckInputResponse(BaseModel):
    allowed: bool
    refused: bool = False
    refusal_reason: Optional[str] = None
    refusal_message: Optional[str] = None
    sanitized_query: str = ""
    has_pii: bool = False
    pii_types: List[str] = Field(default_factory=list)
    critical_pii_masked: bool = False
    needs_privacy_confirm: bool = False
    privacy_warning: Optional[str] = None


class SessionTitleRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)


class SessionTitleResponse(BaseModel):
    title: str


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    history: List[ChatMessage] = Field(default_factory=list)
    user_documents: List[UserDocumentAttachment] = Field(default_factory=list)
    use_rag: bool = True
    enable_consistency: bool = False
    enable_nli: bool = True
    n_consistency_samples: int = Field(2, ge=1, le=5)
    privacy_confirmed: bool = False
    # 模型选择：None/"auto" = 跟随全局默认（global_model 或 .env DEFAULT_API_MODEL）；
    # 具体 id（如 "qwen3.7-plus"/"deepseek-v4-flash-0731"）；"local" = 离线引擎
    model: Optional[str] = None
    # 前端设置面板保存的全局默认模型 id（Auto 解析用，最终以后端为准）
    global_model: Optional[str] = None


class ChatStreamRequest(ChatRequest):
    message_id: str = Field(..., min_length=1, max_length=128)


class ChatResponse(BaseModel):
    query: str
    answer: str
    use_rag: bool
    retrieved_articles: List[Dict[str, Any]]
    citation_verification: Dict[str, Any]
    consistency: Optional[Dict[str, Any]] = None
    trust: Optional[Dict[str, Any]] = None
    regeneration_attempts: int = 0
    refused: bool = False
    refusal_reason: Optional[str] = None
    input_guard: Optional[Dict[str, Any]] = None
    intent: Optional[Dict[str, Any]] = None
    query_rewrite: Optional[Dict[str, Any]] = None
    rag_used: bool = False
    # 实际使用的模型（Auto 解析后落定的结果，供前端展示）
    model_id: Optional[str] = None
    model_name: Optional[str] = None
    # 任务调度结果（时效查询/合同审查/默认问答；Task 3 起透传，旧前端忽略即可）
    task: Optional[Dict[str, Any]] = None
    # 时效查询的确定性证据（task.task_type == "validity_check" 时非空）
    validity_evidence: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    status: str
    laws_loaded: bool


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class LoginResponse(BaseModel):
    token: str
    username: str
    display_name: str


class AuthVerifyRequest(BaseModel):
    token: str = Field(..., min_length=1)


class AuthVerifyResponse(BaseModel):
    valid: bool
    username: Optional[str] = None
    display_name: Optional[str] = None
