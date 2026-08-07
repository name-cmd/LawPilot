import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent

# 从项目根目录 .env 加载环境变量（如 DASHSCOPE_API_KEY）；无 .env 文件时静默跳过
load_dotenv(BASE_DIR / ".env")


class Config:
    BASE_DIR = BASE_DIR

    # Model paths (local)
    LLM_MODEL_PATH = str(BASE_DIR / "models" / "Qwen2.5-7B-Instruct")
    EMBEDDING_MODEL_PATH = str(BASE_DIR / "models" / "bge-base-zh-v1.5")

    # Data paths
    RAW_DATA_DIR = str(BASE_DIR / "data" / "raw")
    PROCESSED_DATA_DIR = str(BASE_DIR / "data" / "processed")

    # Vector store
    LAW_DB_DIR = str(BASE_DIR / "law_db")
    COLLECTION_NAME = "chinese_laws"

    # Embedding settings
    EMBEDDING_DEVICE = "cuda"
    EMBEDDING_BATCH_SIZE = 32

    # LLM settings
    LLM_DEVICE = "cuda"
    LLM_MAX_NEW_TOKENS = 1024
    LLM_TEMPERATURE = 0.4

    # ---- LLM provider（双模式：本地推理 / 阿里云百炼 API）----
    # "api" = 百炼 API（默认）| "local" = 本地 Qwen2.5-7B；支持环境变量 LLM_PROVIDER 覆盖
    LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "api")
    # 百炼 OpenAI 兼容接口地址（华北2北京地域）
    API_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    # 默认主模型：qwen3.7-plus（性价比高、256K 上下文；免费额度用尽可切 qwen3.6-plus-2026-04-02 快照版，额度独立）
    # 支持环境变量 API_MODEL 覆盖（.env 中设置，与 .env.example 说明保持一致）
    API_MODEL = os.environ.get("API_MODEL", "qwen3.7-plus")
    # 全局默认模型（Auto 跟随；可被前端设置面板传回的 global_model 覆盖）。
    # 可选值：qwen3.7-plus / qwen-turbo / qwen3.7-max / deepseek-v4-flash-0731 /
    #         deepseek-v4-pro / kimi-k2.6 / glm-5.2（详见 src/llm/model_registry.py）
    DEFAULT_API_MODEL = os.environ.get("DEFAULT_API_MODEL", API_MODEL)
    # API Key 只从环境变量 / .env 读取，绝不硬编码（阿里云百炼控制台 → API-KEY 管理）
    API_KEY_ENV = "DASHSCOPE_API_KEY"
    # qwen3 系列默认开启思考模式（多输出推理 token、增加成本与延迟），显式关闭
    # None = 不传该参数 | False = 显式关闭思考
    API_ENABLE_THINKING = False
    API_TIMEOUT_SECONDS = 60
    API_MAX_RETRIES = 3
    API_RETRY_BACKOFF_SECONDS = 1.0
    # 打印每次调用的 token 用量（为阶段四「效果对比」成本数据做准备）
    API_LOG_USAGE = True

    # Citation verifier thresholds
    ROUGE_THRESHOLD = 0.3
    COSINE_THRESHOLD = 0.6
    CONTENT_MATCH_THRESHOLD = 0.7
    # Lower bar for detecting text belongs to a different article number
    MISMATCH_SUGGEST_THRESHOLD = 0.55
    NLI_THRESHOLD = 0.5
    TOP_K_RETRIEVAL = 5

    # Answer pipeline
    CITATION_RETRY_THRESHOLD = 0.65
    MAX_REGENERATION_ATTEMPTS = 1
    RETRIEVAL_MIN_RELEVANCE = 0.35  # below this, skip RAG injection
    ENABLE_INTENT_ROUTING = True
    ENABLE_QUERY_REWRITE = True

    # LegalTrust scorer weights (sum = 1.0)
    TRUST_WEIGHTS = {
        "truthfulness": 0.30,
        "safety": 0.25,
        "fairness": 0.10,
        "robustness": 0.10,
        "privacy": 0.15,
        "ethics": 0.10,
    }

    # Multi-turn chat
    MAX_HISTORY_MESSAGES = 20  # max user+assistant turns kept in context

    # User document upload
    DOC_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
    DOC_MAX_CONTEXT_CHARS = 12000  # max chars injected per request
    DOC_MAX_ATTACHMENTS = 5
    # OCR backend: "rapidocr" (default, ONNX) or "paddleocr"
    OCR_BACKEND = "rapidocr"

    # Streaming + async verification
    ENABLE_STREAMING = True
    VERIFICATION_WS_TTL_SEC = 300

    # Law validity
    LAW_REGISTRY_PATH = str(BASE_DIR / "data" / "law_registry.json")
    LAW_REPEALS_PATH = str(BASE_DIR / "data" / "processed" / "law_repeals.json")

    # Self-consistency settings
    N_SAMPLES = 5
    TEMPERATURE_RANGE = [0.3, 0.5, 0.7, 0.9, 1.1]
    CONSISTENCY_THRESHOLD = 0.75

    # NLI model (downloaded from HuggingFace at runtime)
    NLI_MODEL_NAME = str(BASE_DIR / "models" / "Erlangshen-Roberta-330M-NLI")
