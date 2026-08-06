"""
LawTrust (法信通) FastAPI backend.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.config import Config
from src.knowledge_base.embedder import LawEmbedder
from src.knowledge_base.vector_store import LawVectorStore
from src.llm.qwen_model import QwenModel
from src.citation_verifier.citation_verifier import CitationVerifier
from src.uncertainty.self_consistency import SelfConsistencyChecker
from src.pipeline.answer_pipeline import AnswerPipeline
from src.trust_eval.legal_trust_scorer import LegalTrustScorer
from src.guardrails.input_guard import InputGuard
from src.guardrails.session_title import generate_session_title

import secrets

from web.backend.schemas import (
    AuthVerifyRequest,
    AuthVerifyResponse,
    ChatRequest,
    ChatResponse,
    ChatStreamRequest,
    CheckInputRequest,
    CheckInputResponse,
    DocumentExtractResponse,
    HealthResponse,
    LoginRequest,
    LoginResponse,
    SessionTitleRequest,
    SessionTitleResponse,
)
from src.document_processing import DocumentExtractor
from web.backend.task_registry import TaskStatus, get_task_registry
from web.backend.ws_manager import get_ws_manager
from web.backend.verification_worker import run_verification_task

# 测试阶段固定账号（生产环境应改为数据库 + 哈希密码）
_AUTH_USERS = {"root": "123456"}
_active_tokens: dict[str, str] = {}  # token -> username

_pipeline: Optional[AnswerPipeline] = None
_store: Optional[LawVectorStore] = None
_input_guard = InputGuard()
_trust_scorer = LegalTrustScorer()
_doc_extractor = DocumentExtractor()


def _empty_citation_verification() -> dict:
    return {
        "extracted_citations": [],
        "implicit_claims": [],
        "overall_citation_score": 0.0,
        "summary": "",
    }


def _build_refusal_response(query: str, guard_result) -> dict:
    trust = _trust_scorer.score(
        query=query,
        response=guard_result.refusal_message or "",
        citation_report={"overall_citation_score": 0.0, "extracted_citations": []},
    )
    return {
        "query": query,
        "answer": guard_result.refusal_message or "",
        "use_rag": False,
        "retrieved_articles": [],
        "citation_verification": _empty_citation_verification(),
        "consistency": None,
        "trust": trust,
        "regeneration_attempts": 0,
        "refused": True,
        "refusal_reason": guard_result.refusal_reason,
        "input_guard": guard_result.to_dict(),
    }


def _build_pipeline() -> AnswerPipeline:
    embedder = LawEmbedder()
    store = LawVectorStore(persist_directory=Config.LAW_DB_DIR, embedder=embedder)
    store.load()
    model = QwenModel()
    verifier = CitationVerifier(
        vector_store=store,
        embedder=embedder,
        enable_nli=True,
    )
    consistency = SelfConsistencyChecker(model=model, embedder=embedder)
    trust_scorer = LegalTrustScorer()
    return AnswerPipeline(
        store=store,
        model=model,
        verifier=verifier,
        consistency=consistency,
        trust_scorer=trust_scorer,
    ), store


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pipeline, _store
    try:
        _pipeline, _store = _build_pipeline()
    except Exception as e:
        print(f"Warning: pipeline init deferred: {e}")
        _pipeline, _store = None, None
    yield


app = FastAPI(
    title="LawTrust 法信通",
    description="可信法律智能问答与多维可信评估平台",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def no_cache_ui_html(request, call_next):
    """/ui 的入口 HTML 禁止缓存：构建后浏览器必须加载最新 index.html，
    否则浏览器可能用缓存的旧入口（引用已删除的旧 JS hash）导致页面行为停留在旧版本。"""
    response = await call_next(request)
    if request.url.path.startswith("/ui") and (
        request.url.path.endswith(".html") or request.url.path.endswith("/")
    ):
        response.headers["Cache-Control"] = "no-cache"
    return response


# 前端静态目录三级回退：
#   1. dist/    —— 新前端（Vite 构建产物，npm run build 生成）
#   2. legacy/  —— 旧版单文件页面（渐进迁移期的回退版本）
#   3. frontend/ —— 兜底
# 注：挂载在服务启动时确定，构建后需重启后端才生效（reload=False）
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"
LEGACY_DIR = FRONTEND_DIR / "legacy"

frontend_root = None
if DIST_DIR.exists():
    frontend_root = DIST_DIR
elif (LEGACY_DIR / "index.html").exists():
    frontend_root = LEGACY_DIR
elif FRONTEND_DIR.exists():
    frontend_root = FRONTEND_DIR
if frontend_root is not None:
    app.mount("/ui", StaticFiles(directory=str(frontend_root), html=True), name="ui")

FIGURE_DIR = ROOT / "figure"
if FIGURE_DIR.exists():
    app.mount("/figure", StaticFiles(directory=str(FIGURE_DIR)), name="figure")


@app.post("/api/auth/login", response_model=LoginResponse)
def login(req: LoginRequest):
    expected = _AUTH_USERS.get(req.username)
    if expected is None or expected != req.password:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = secrets.token_urlsafe(32)
    _active_tokens[token] = req.username
    return LoginResponse(
        token=token,
        username=req.username,
        display_name=req.username,
    )


@app.post("/api/auth/verify", response_model=AuthVerifyResponse)
def verify_auth(req: AuthVerifyRequest):
    username = _active_tokens.get(req.token)
    if not username:
        return AuthVerifyResponse(valid=False)
    return AuthVerifyResponse(valid=True, username=username, display_name=username)


@app.post("/api/auth/logout")
def logout(req: AuthVerifyRequest):
    _active_tokens.pop(req.token, None)
    return {"ok": True}


@app.get("/api/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok" if _pipeline else "degraded",
        laws_loaded=_store is not None,
    )


@app.post("/api/check-input", response_model=CheckInputResponse)
def check_input(req: CheckInputRequest):
    result = _input_guard.check(req.query, privacy_confirmed=req.privacy_confirmed)
    return CheckInputResponse(**result.to_dict())


@app.post("/api/session-title", response_model=SessionTitleResponse)
def session_title(req: SessionTitleRequest):
    return SessionTitleResponse(title=generate_session_title(req.query))


def _serialize_user_documents(docs) -> list[dict]:
    return [
        {
            "filename": d.filename,
            "text": d.text,
            "format": d.format,
            "char_count": d.char_count,
        }
        for d in (docs or [])
    ]


@app.post("/api/documents/extract", response_model=DocumentExtractResponse)
async def extract_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    if not DocumentExtractor.is_supported(file.filename):
        exts = ", ".join(DocumentExtractor.supported_extensions())
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式，支持：{exts}",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    try:
        result = _doc_extractor.extract_bytes(data, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文档解析失败：{e}") from e
    if not result.text.strip():
        raise HTTPException(
            status_code=422,
            detail={
                "message": "未能从文档中提取到文字",
                "warnings": result.warnings,
            },
        )
    return DocumentExtractResponse(**result.to_dict())


@app.get("/api/documents/supported-formats")
def supported_document_formats():
    return {
        "extensions": DocumentExtractor.supported_extensions(),
        "max_upload_mb": Config.DOC_MAX_UPLOAD_BYTES // 1024 // 1024,
        "max_attachments": Config.DOC_MAX_ATTACHMENTS,
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    guard = _input_guard.check(req.query, privacy_confirmed=req.privacy_confirmed)

    if guard.refused:
        return ChatResponse(**_build_refusal_response(req.query, guard))

    if guard.needs_privacy_confirm:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "privacy_confirm_required",
                "message": guard.privacy_warning,
                "pii_types": guard.pii_types,
                "sanitized_query": guard.sanitized_query,
            },
        )

    query = guard.sanitized_query

    if _pipeline is None:
        raise HTTPException(
            status_code=503,
            detail="服务未就绪：请确认向量库已构建且模型路径正确",
        )
    try:
        history = [{"role": m.role, "content": m.content} for m in req.history]
        result = _pipeline.run(
            query=query,
            use_rag=req.use_rag,
            enable_consistency=req.enable_consistency,
            n_consistency_samples=req.n_consistency_samples,
            enable_nli=req.enable_nli,
            history=history or None,
            user_documents=_serialize_user_documents(req.user_documents),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    result["query"] = query
    result["refused"] = False
    result["refusal_reason"] = None
    result["input_guard"] = guard.to_dict()
    return ChatResponse(**result)


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/chat/stream")
def chat_stream(req: ChatStreamRequest, background_tasks: BackgroundTasks):
    guard = _input_guard.check(req.query, privacy_confirmed=req.privacy_confirmed)

    if guard.refused:
        raise HTTPException(
            status_code=400,
            detail={"code": "refused", "message": guard.refusal_message},
        )

    if guard.needs_privacy_confirm:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "privacy_confirm_required",
                "message": guard.privacy_warning,
                "pii_types": guard.pii_types,
                "sanitized_query": guard.sanitized_query,
            },
        )

    query = guard.sanitized_query

    if _pipeline is None:
        raise HTTPException(
            status_code=503,
            detail="服务未就绪：请确认向量库已构建且模型路径正确",
        )

    history = [{"role": m.role, "content": m.content} for m in req.history]
    message_id = req.message_id
    get_task_registry().create(message_id)

    def event_generator():
        try:
            ctx, meta = _pipeline.run_fast(
                query=query,
                use_rag=req.use_rag,
                history=history or None,
                user_documents=_serialize_user_documents(req.user_documents),
            )

            if ctx.intent.intent in ("greeting", "general_non_legal"):
                parts = []
                for chunk in _pipeline.generate_answer_stream(ctx):
                    parts.append(chunk)
                    yield _sse_event("token", {"content": chunk})
                answer = "".join(parts)
                yield _sse_event(
                    "done",
                    {
                        "answer": answer,
                        "non_legal": True,
                        "intent": ctx.intent.to_dict(),
                    },
                )
                return

            if meta:
                yield _sse_event("meta", meta)

            parts = []
            for chunk in _pipeline.generate_answer_stream(ctx):
                parts.append(chunk)
                yield _sse_event("token", {"content": chunk})
            answer = "".join(parts)

            partial_trust = None
            if _trust_scorer and ctx.rag_used:
                partial_trust = _trust_scorer.score_fast(query, answer)

            yield _sse_event(
                "done",
                {
                    "answer": answer,
                    "message_id": message_id,
                    "trust": partial_trust,
                },
            )

            if ctx.rag_used and Config.ENABLE_STREAMING:
                background_tasks.add_task(
                    run_verification_task,
                    _pipeline,
                    message_id,
                    ctx,
                    answer,
                    req.enable_consistency,
                    req.n_consistency_samples,
                )
        except Exception as e:
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.websocket("/ws/verification/{message_id}")
async def verification_ws(websocket: WebSocket, message_id: str):
    ws_manager = get_ws_manager()
    registry = get_task_registry()
    await ws_manager.connect(message_id, websocket)

    # If verification already finished, send immediately
    existing = registry.get(message_id)
    if existing and existing.status == TaskStatus.DONE and existing.result:
        await websocket.send_text(
            json.dumps(existing.result, ensure_ascii=False)
        )

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(message_id, websocket)


@app.get("/")
def root():
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/ui/index.html")
