"""
LawTrust (法信通) FastAPI backend.
"""
import asyncio
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
from src.llm.model_registry import (
    ModelSpec,
    check_local_engine_ready,
    get_api_model_list,
    resolve_model_spec,
)
from src.citation_verifier.citation_verifier import CitationVerifier
from src.uncertainty.self_consistency import SelfConsistencyChecker
from src.pipeline.answer_pipeline import AnswerPipeline
from src.trust_eval.legal_trust_scorer import LegalTrustScorer
from src.guardrails.input_guard import InputGuard
from src.guardrails.session_title import generate_session_title

from web.backend.schemas import (
    AuthVerifyRequest,
    AuthVerifyResponse,
    ChangePasswordRequest,
    ChatRequest,
    ChatResponse,
    ChatStreamRequest,
    CheckInputRequest,
    CheckInputResponse,
    DocumentExtractResponse,
    HealthResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    SessionTitleRequest,
    SessionTitleResponse,
    UserDataFetchRequest,
    UserDataResponse,
    UserDataSaveRequest,
    UserProfileResponse,
    UserProfileUpdateRequest,
)
from src.document_processing import DocumentExtractor
from web.backend.task_registry import TaskStatus, get_task_registry
from web.backend.user_data import UserDataStore
from web.backend.user_store import UserStore
from web.backend.session_manager import SessionManager
from web.backend.ws_manager import get_ws_manager
from web.backend.verification_worker import bind_main_loop, run_verification_task

# 多用户账号体系（阶段三）：用户注册表（哈希密码 + 每用户 API Key）、
# 服务端会话管理（Token TTL + JSON 持久化）、每用户数据（会话/收藏/资料）
_user_store = UserStore()
_session_mgr = SessionManager()
_user_data = UserDataStore()

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


def _resolve_model(req_model: Optional[str], global_model: Optional[str]) -> ModelSpec:
    """解析用户模型选择 → 具体模型条目。

    优先级：请求显式 id > auto（→ 前端设置面板的 global_model → .env DEFAULT_API_MODEL）。
    未知 id 或离线引擎不可用 → HTTP 400 中文提示。
    """
    mid = req_model or "auto"
    if mid == "auto":
        mid = global_model or Config.DEFAULT_API_MODEL
    if mid == "local":
        ready = check_local_engine_ready()
        if not ready["available"]:
            raise HTTPException(
                status_code=400,
                detail=f"离线引擎当前不可用：{ready['reason']}（需 CUDA GPU 与本地模型文件）",
            )
        raise HTTPException(
            status_code=400,
            detail="离线引擎暂未启用：请通过服务端配置启动本地模式",
        )
    try:
        return resolve_model_spec(mid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


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
    # 绑定主事件循环：后台核验线程通过它把 WebSocket 结果调度回主循环广播
    bind_main_loop(asyncio.get_running_loop())
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


@app.post("/api/auth/register", response_model=LoginResponse)
def register(req: RegisterRequest):
    """注册新用户：成功即自动登录（直接返回 token）。"""
    from web.backend.user_store import UsernameTakenError

    try:
        user = _user_store.register(req.username, req.password)
    except UsernameTakenError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    token = _session_mgr.create(user.username)
    return LoginResponse(
        token=token,
        username=user.username,
        display_name=user.display_name,
    )


@app.post("/api/auth/login", response_model=LoginResponse)
def login(req: LoginRequest):
    user = _user_store.authenticate(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = _session_mgr.create(user.username)
    return LoginResponse(
        token=token,
        username=user.username,
        display_name=user.display_name,
    )


@app.post("/api/auth/verify", response_model=AuthVerifyResponse)
def verify_auth(req: AuthVerifyRequest):
    username = _session_mgr.verify(req.token)
    if not username:
        return AuthVerifyResponse(valid=False)
    return AuthVerifyResponse(
        valid=True,
        username=username,
        display_name=_user_store.display_name(username),
    )


@app.post("/api/auth/logout")
def logout(req: AuthVerifyRequest):
    _session_mgr.revoke(req.token)
    return {"ok": True}


@app.post("/api/auth/change-password")
def change_password(req: ChangePasswordRequest):
    """修改密码：校验旧密码 → 重新哈希 → 吊销该用户其他设备的 Token。"""
    from web.backend.user_store import validate_password

    username = _require_user(req)
    if not _user_store.authenticate(username, req.old_password):
        raise HTTPException(status_code=400, detail="原密码错误")
    reason = validate_password(req.new_password)
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    _user_store.change_password(username, req.new_password)
    revoked = _session_mgr.revoke_others(username, keep_token=req.token)
    return {"ok": True, "revoked_devices": revoked}


def _require_user(req: AuthVerifyRequest) -> str:
    """校验 Token，返回用户名；无效抛 401。"""
    username = _session_mgr.verify(req.token)
    if not username:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return username


# ---- 用户数据读写（阶段三 3.2：登录后拉取恢复，双写异步提交）----


@app.post("/api/user/data", response_model=UserDataResponse)
def fetch_user_data(req: UserDataFetchRequest):
    """拉取该用户全部会话与收藏（exists=false 表示服务端无数据文件=首次登录）。"""
    username = _require_user(req)
    data = _user_data.load(username)
    return UserDataResponse(
        sessions=data["sessions"],
        favorites=data["favorites"],
        exists=data["exists"],
    )


@app.post("/api/user/data/save")
def save_user_data(req: UserDataSaveRequest):
    """整包保存会话与收藏（前端双写防抖提交）。"""
    username = _require_user(req)
    _user_data.save_data(username, req.sessions, req.favorites)
    return {"ok": True}


@app.post("/api/user/profile", response_model=UserProfileResponse)
def fetch_user_profile(req: UserDataFetchRequest):
    username = _require_user(req)
    return UserProfileResponse(**_user_data.get_profile(username))


@app.post("/api/user/clear")
def clear_user_data(req: UserDataFetchRequest):
    """清空该账号全部个人数据（会话/收藏/资料），保留账号与自配 API Key。"""
    username = _require_user(req)
    _user_data.clear_user_data(username)
    return {"ok": True}


@app.post("/api/user/profile/save", response_model=UserProfileResponse)
def save_user_profile(req: UserProfileUpdateRequest):
    username = _require_user(req)
    patch = {
        k: getattr(req, k)
        for k in ("display_name", "bio", "avatar_color", "avatar_data", "api_key")
        if getattr(req, k) is not None
    }
    # 用户自配 API Key 同步写入注册表（问答时从注册表取 Key，数据文件不重复存）
    if "api_key" in patch:
        _user_store.update_api_key(username, patch["api_key"])
        # 归一化（空串 → None 表示未配置）：save_profile 会跳过 None 字段，
        # 清空场景需存空串显式覆盖旧值，保证资料文件与注册表一致
        user = _user_store.get_user(username)
        patch["api_key"] = (user.api_key if user else None) or ""
    return UserProfileResponse(**_user_data.save_profile(username, patch))


def _resolve_user_api_key(req_token: Optional[str]) -> Optional[str]:
    """请求带有效登录 Token → 返回该用户自配 API Key；未登录/未配置 → None
    （None 表示回退服务端 .env 的 DASHSCOPE_API_KEY，root 默认即此路径）。
    Token 无效不强制鉴权（指南阶段三 3.4 预留能力），仅回退服务端 Key。"""
    if not req_token:
        return None
    username = _session_mgr.verify(req_token)
    if not username:
        return None
    user = _user_store.get_user(username)
    return user.api_key if user else None


@app.get("/api/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok" if _pipeline else "degraded",
        laws_loaded=_store is not None,
    )


@app.get("/api/models")
def list_models():
    """模型目录：前端模型选择器与设置面板的数据源（新增模型 = 注册表加一行，前端零改动）。"""
    return {
        "api_models": [
            {
                "id": m.id,
                "display_name": m.display_name,
                "provider": m.provider,
                "price_tier": m.price_tier,
                "capabilities": m.capabilities,
                "is_default": m.is_default,
                "is_enabled": m.is_enabled,
                "thinking_supported": m.thinking_supported,
            }
            for m in get_api_model_list()
        ],
        "local_engine": check_local_engine_ready(),
        "default_model": Config.DEFAULT_API_MODEL,
    }


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
    spec = _resolve_model(req.model, req.global_model)
    user_api_key = _resolve_user_api_key(req.token)
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
            model_id=spec.id,
            api_key=user_api_key,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    result["query"] = query
    result["refused"] = False
    result["refusal_reason"] = None
    result["input_guard"] = guard.to_dict()
    result["model_id"] = spec.id
    result["model_name"] = spec.display_name
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

    spec = _resolve_model(req.model, req.global_model)
    user_api_key = _resolve_user_api_key(req.token)
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
                model_id=spec.id,
                api_key=user_api_key,
            )

            # 首事件必发 meta：携带实际使用的模型（流式中断时消息也有模型记录），
            # 法律类回答再并入 RAG 检索等元信息
            yield _sse_event(
                "meta",
                {
                    "model_id": spec.id,
                    "model_name": spec.display_name,
                    **(meta or {}),
                },
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
                        "model_id": spec.id,
                        "model_name": spec.display_name,
                    },
                )
                return

            # ---- 智能体工具模式：法律问答 + 工具可用（API 引擎） ----
            use_agent = (
                Config.AGENT_ENABLE_TOOLS
                and ctx.task is not None
                and ctx.task.task_type == "legal_qa"
                and _pipeline.model.supports_tools(spec.id)
            )
            if use_agent:
                from src.agents.agent_loop import AgentToolLoop
                from src.knowledge_base.retrieval_utils import merge_unique_docs
                from src.llm.qwen_model import TOOL_GUIDANCE_SUFFIX

                # 工具模式专用提示词段：仅此分支注入，非工具路径不携带
                ctx.system_prompt = ctx.system_prompt + TOOL_GUIDANCE_SUFFIX
                loop = AgentToolLoop(
                    _pipeline.model, _pipeline.store,
                    validity=(_pipeline.verifier.validity if _pipeline.verifier else None),
                )
                parts = []
                for ev in loop.stream(ctx, model_id=spec.id):
                    if isinstance(ev, str):
                        parts.append(ev)
                        yield _sse_event("token", {"content": ev})
                    else:
                        yield _sse_event("agent_status", ev.to_dict())
                answer = "".join(parts)
                tool_trace = [s.to_dict() for s in loop.trace]
                if loop.found_docs:
                    ctx.retrieved_docs = merge_unique_docs(ctx.retrieved_docs, loop.found_docs)
                    ctx.rag_used = True
            else:
                parts = []
                for chunk in _pipeline.generate_answer_stream(ctx):
                    parts.append(chunk)
                    yield _sse_event("token", {"content": chunk})
                answer = "".join(parts)
                tool_trace = []

            partial_trust = None
            if _trust_scorer and ctx.rag_used:
                partial_trust = _trust_scorer.score_fast(query, answer)

            yield _sse_event(
                "done",
                {
                    "answer": answer,
                    "message_id": message_id,
                    "trust": partial_trust,
                    "model_id": spec.id,
                    "model_name": spec.display_name,
                    "task": ctx.task.to_dict() if ctx.task else None,
                    "validity_evidence": ctx.validity_evidence,
                    "tool_trace": tool_trace,
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
