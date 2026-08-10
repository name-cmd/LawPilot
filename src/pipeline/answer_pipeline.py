"""
Unified orchestration: intent routing → query rewrite → RAG retrieval
→ generation → citation verification → optional regeneration → trust scoring.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, Generator, List, Optional, Tuple

from langchain_core.documents import Document

from src.config import Config
from src.llm.qwen_model import QwenModel, get_system_prompt
from src.llm.rag_context import format_retrieved_articles
from src.document_processing.document_context import format_user_documents
from src.citation_verifier.citation_verifier import CitationVerifier
from src.uncertainty.self_consistency import SelfConsistencyChecker
from src.knowledge_base.retrieval_utils import article_key, format_article_record
from src.pipeline.intent_router import IntentResult, classify_intent
from src.pipeline.query_rewriter import (
    RewriteResult,
    is_retrieval_relevant,
    rewrite_for_retrieval,
)
from src.agents.task_scheduler import TaskDecision, classify_task
from src.knowledge_base.law_validity import LawValidityService, build_validity_evidence


_REGENERATE_PROMPT_SUFFIX = """
上次回答的引用核验未通过，请在保持【结论】【法律分析】【依据法条】结构的前提下修正：
{feedback}
修正要求：仅引用参考法条；条号与法律名称须正确；引号内须逐字复述「原文」字段。"""

_FOCUS_REGEN_SUFFIX = """
上次回答偏离了用户核心诉求。用户核心法律问题是：{core_focus}
请围绕上述核心问题重新作答，不要仅因用户附带提及身份证/手机号就只回答证件扣押或隐私条款。
保持【结论】【法律分析】【依据法条】结构。"""

_EMPTY_VERIFICATION = {
    "extracted_citations": [],
    "implicit_claims": [],
    "overall_citation_score": 1.0,
    "summary": "非法律结构化回答，未执行引用核验",
    "validity_warnings": [],
}


@dataclass
class PipelineContext:
    """Shared state between fast path and async verification."""
    query: str
    intent: IntentResult
    rewrite: Optional[RewriteResult] = None
    retrieved_docs: List[Document] = field(default_factory=list)
    retrieval_scores: List[float] = field(default_factory=list)
    rag_used: bool = False
    rag_block: str = ""
    generation_query: str = ""
    intent_hint: Optional[str] = None
    context_docs: Optional[List[str]] = None
    system_prompt: str = ""
    use_rag: bool = True
    history: Optional[List[Dict[str, str]]] = None
    user_documents: Optional[List[Dict]] = None
    # 用户选择的模型 id（"auto" 已在路由层解析为具体 id；None = 走引擎默认）
    model_id: Optional[str] = None
    # 任务调度结果（合同审查 / 时效查询 / 默认法律问答）
    task: Optional[TaskDecision] = None
    # 时效查询的确定性证据（任务类型为 validity_check 时非空）
    validity_evidence: Optional[Dict] = None


class AnswerPipeline:
    def __init__(
        self,
        store,
        model: QwenModel,
        verifier: CitationVerifier,
        consistency: Optional[SelfConsistencyChecker] = None,
        trust_scorer=None,
    ):
        self.store = store
        self.model = model
        self.verifier = verifier
        self.consistency = consistency
        self.trust_scorer = trust_scorer

    def run(
        self,
        query: str,
        use_rag: bool = True,
        enable_consistency: bool = False,
        n_consistency_samples: int = 2,
        enable_nli: bool = True,
        max_regeneration: int = None,
        history: Optional[List[Dict[str, str]]] = None,
        user_documents: Optional[List[Dict]] = None,
        model_id: Optional[str] = None,
    ) -> Dict:
        max_regeneration = (
            max_regeneration
            if max_regeneration is not None
            else Config.MAX_REGENERATION_ATTEMPTS
        )
        user_documents = self._truncate_user_documents(user_documents)

        intent = (
            classify_intent(query, history, user_documents=user_documents)
            if Config.ENABLE_INTENT_ROUTING
            else IntentResult("legal_qa", 1.0, "意图路由已关闭")
        )

        if intent.intent in ("greeting", "general_non_legal"):
            return self._run_non_legal(
                query=query,
                intent=intent,
                history=history,
                user_documents=user_documents,
                model_id=model_id,
            )

        task = classify_task(query, intent, user_documents)

        if task.task_type == "validity_check":
            return self._run_validity(query, intent, task, history, model_id)

        rewrite = (
            rewrite_for_retrieval(query)
            if Config.ENABLE_QUERY_REWRITE
            else RewriteResult(
                original=query,
                cleaned=query,
                retrieval_queries=[query],
                core_focus=query,
                pii_stripped=False,
            )
        )

        retrieved_docs: List[Document] = []
        retrieval_scores: List[float] = []
        rag_used = False
        rag_block = ""

        if use_rag:
            retrieved_docs, retrieval_scores, rag_used = self._retrieve_articles(
                rewrite, history
            )
            if rag_used:
                rag_block = format_retrieved_articles(retrieved_docs)

        generation_query = self._build_generation_query(query, rewrite)
        intent_hint = (
            f"用户核心法律诉求：{rewrite.core_focus}"
            if rewrite.core_focus and rewrite.core_focus != query
            else None
        )
        context_docs = self._build_context_docs(
            rag_block=rag_block,
            user_documents=user_documents,
        )
        system_prompt = get_system_prompt(
            "contract_review" if task.task_type == "contract_review" else "legal_qa"
        )

        response = self.model.generate(
            generation_query,
            system_prompt=system_prompt,
            context_docs=context_docs,
            history=history,
            intent_hint=intent_hint,
            model_id=model_id,
        )

        verification = (
            self.verifier.verify(
                response,
                retrieved_docs=retrieved_docs,
                user_documents=user_documents,
            )
            if rag_used
            else dict(_EMPTY_VERIFICATION)
        )

        attempts = 0
        while (
            attempts < max_regeneration
            and rag_used
            and verification["overall_citation_score"] < Config.CITATION_RETRY_THRESHOLD
            and verification.get("extracted_citations")
        ):
            feedback = self._build_feedback(verification)
            regen_query = generation_query + _REGENERATE_PROMPT_SUFFIX.format(
                feedback=feedback
            )
            response = self.model.generate(
                regen_query,
                system_prompt=system_prompt,
                context_docs=context_docs,
                history=history,
                intent_hint=intent_hint,
                model_id=model_id,
            )
            verification = self.verifier.verify(
                response,
                retrieved_docs=retrieved_docs,
                user_documents=user_documents,
            )
            attempts += 1

        if rag_used and self._needs_focus_regeneration(query, rewrite, response):
            regen_query = generation_query + _FOCUS_REGEN_SUFFIX.format(
                core_focus=rewrite.core_focus
            )
            response = self.model.generate(
                regen_query,
                system_prompt=system_prompt,
                context_docs=context_docs,
                history=history,
                intent_hint=intent_hint,
                model_id=model_id,
            )
            verification = self.verifier.verify(
                response,
                retrieved_docs=retrieved_docs,
                user_documents=user_documents,
            )

        consistency_report = None
        if enable_consistency and self.consistency and rag_used:
            consistency_report = self.consistency.check(
                generation_query,
                n_samples=n_consistency_samples,
                temperatures=Config.TEMPERATURE_RANGE[:n_consistency_samples],
                context_docs=context_docs,
                history=history,
                model_id=model_id,
            )

        trust_report = None
        if self.trust_scorer:
            trust_report = self.trust_scorer.score_full(
                query=query,
                response=response,
                citation_report=verification if rag_used else None,
                consistency_report=consistency_report,
            )

        return {
            "query": query,
            "answer": response,
            "use_rag": use_rag and rag_used,
            "retrieved_articles": self._format_retrieved(
                retrieved_docs, retrieval_scores
            ),
            "citation_verification": verification,
            "consistency": consistency_report,
            "trust": trust_report,
            "regeneration_attempts": attempts,
            "intent": intent.to_dict(),
            "query_rewrite": rewrite.to_dict(),
            "rag_used": rag_used,
        }

    def prepare_context(
        self,
        query: str,
        use_rag: bool = True,
        history: Optional[List[Dict[str, str]]] = None,
        user_documents: Optional[List[Dict]] = None,
        model_id: Optional[str] = None,
    ) -> PipelineContext:
        user_documents = self._truncate_user_documents(user_documents)

        intent = (
            classify_intent(query, history, user_documents=user_documents)
            if Config.ENABLE_INTENT_ROUTING
            else IntentResult("legal_qa", 1.0, "意图路由已关闭")
        )

        if intent.intent == "greeting":
            # 寒暄：不需要文档内容，保持原样（不注入、不用文档分析提示词）
            return PipelineContext(
                query=query,
                intent=intent,
                history=history,
                use_rag=False,
                system_prompt=get_system_prompt("greeting"),
                user_documents=user_documents,
                model_id=model_id,
            )

        if intent.intent == "general_non_legal":
            # 非法律文档分析：注入文档全文（此前 context_docs=None 丢弃文档，
            # 模型读不到——「文档读不到」问题的根源结构），提示词用文档分析版
            return PipelineContext(
                query=query,
                intent=intent,
                history=history,
                use_rag=False,
                system_prompt=get_system_prompt(
                    "general_non_legal", document_mode=bool(user_documents)
                ),
                context_docs=self._build_context_docs(user_documents=user_documents),
                user_documents=user_documents,
                model_id=model_id,
            )

        task = classify_task(query, intent, user_documents)

        # 时效查询快路径：直查注册表 → 确定性证据 + 模型润色（不检索、不核验）
        if task.task_type == "validity_check":
            validity = self.verifier.validity if self.verifier else LawValidityService()
            evidence = build_validity_evidence(task.law_name, validity)
            return PipelineContext(
                query=query,
                intent=intent,
                task=task,
                history=history,
                use_rag=False,
                system_prompt=get_system_prompt("validity_check"),
                generation_query=query,
                context_docs=[evidence["text"]],
                validity_evidence=evidence,
                user_documents=user_documents,
                model_id=model_id,
            )

        rewrite = (
            rewrite_for_retrieval(query)
            if Config.ENABLE_QUERY_REWRITE
            else RewriteResult(
                original=query,
                cleaned=query,
                retrieval_queries=[query],
                core_focus=query,
                pii_stripped=False,
            )
        )

        retrieved_docs: List[Document] = []
        retrieval_scores: List[float] = []
        rag_used = False
        rag_block = ""

        if use_rag:
            retrieved_docs, retrieval_scores, rag_used = self._retrieve_articles(
                rewrite, history
            )
            if rag_used:
                rag_block = format_retrieved_articles(retrieved_docs)

        generation_query = self._build_generation_query(query, rewrite)
        intent_hint = (
            f"用户核心法律诉求：{rewrite.core_focus}"
            if rewrite.core_focus and rewrite.core_focus != query
            else None
        )
        context_docs = self._build_context_docs(
            rag_block=rag_block,
            user_documents=user_documents,
        )

        return PipelineContext(
            query=query,
            intent=intent,
            task=task,
            rewrite=rewrite,
            retrieved_docs=retrieved_docs,
            retrieval_scores=retrieval_scores,
            rag_used=rag_used,
            rag_block=rag_block,
            generation_query=generation_query,
            intent_hint=intent_hint,
            context_docs=context_docs,
            system_prompt=get_system_prompt(
                "contract_review" if task.task_type == "contract_review" else "legal_qa"
            ),
            use_rag=use_rag,
            history=history,
            user_documents=user_documents,
            model_id=model_id,
        )

    def generate_answer_stream(
        self, ctx: PipelineContext
    ) -> Generator[str, None, None]:
        if ctx.intent.intent in ("greeting", "general_non_legal"):
            yield from self.model.generate_stream(
                ctx.query,
                system_prompt=ctx.system_prompt,
                context_docs=ctx.context_docs,
                history=ctx.history,
                model_id=ctx.model_id,
            )
            return

        yield from self.model.generate_stream(
            ctx.generation_query,
            system_prompt=ctx.system_prompt,
            context_docs=ctx.context_docs,
            history=ctx.history,
            intent_hint=ctx.intent_hint,
            model_id=ctx.model_id,
        )

    def run_fast(
        self,
        query: str,
        use_rag: bool = True,
        history: Optional[List[Dict[str, str]]] = None,
        user_documents: Optional[List[Dict]] = None,
        model_id: Optional[str] = None,
    ) -> Tuple[PipelineContext, Optional[Dict]]:
        """Prepare context and metadata without LLM generation or verification."""
        ctx = self.prepare_context(
            query,
            use_rag=use_rag,
            history=history,
            user_documents=user_documents,
            model_id=model_id,
        )

        if ctx.intent.intent in ("greeting", "general_non_legal"):
            return ctx, None

        meta = {
            "use_rag": ctx.use_rag and ctx.rag_used,
            "retrieved_articles": self._format_retrieved(
                ctx.retrieved_docs, ctx.retrieval_scores
            ),
            "intent": ctx.intent.to_dict(),
            "query_rewrite": ctx.rewrite.to_dict() if ctx.rewrite else None,
            "rag_used": ctx.rag_used,
            "citation_verification": {
                **_EMPTY_VERIFICATION,
                "summary": "引用核验进行中…",
            },
            "verification_status": "pending",
            "task": ctx.task.to_dict() if ctx.task else None,
            "validity_evidence": ctx.validity_evidence,
        }
        return ctx, meta

    def run_verification(
        self,
        ctx: PipelineContext,
        response: str,
        enable_consistency: bool = False,
        n_consistency_samples: int = 2,
    ) -> Dict:
        """Full citation verification and trust scoring (no regeneration)."""
        if ctx.intent.intent in ("greeting", "general_non_legal"):
            return {
                "citation_verification": dict(_EMPTY_VERIFICATION),
                "consistency": None,
                "trust": None,
                "regeneration_attempts": 0,
                "validity_warnings": [],
            }

        verification = (
            self.verifier.verify(
                response,
                retrieved_docs=ctx.retrieved_docs,
                user_documents=ctx.user_documents,
            )
            if ctx.rag_used
            else dict(_EMPTY_VERIFICATION)
        )

        consistency_report = None
        if enable_consistency and self.consistency and ctx.rag_used:
            consistency_report = self.consistency.check(
                ctx.generation_query,
                n_samples=n_consistency_samples,
                temperatures=Config.TEMPERATURE_RANGE[:n_consistency_samples],
                context_docs=ctx.context_docs,
                history=ctx.history,
                model_id=ctx.model_id,
            )

        trust_report = None
        if self.trust_scorer:
            trust_report = self.trust_scorer.score_full(
                query=ctx.query,
                response=response,
                citation_report=verification if ctx.rag_used else None,
                consistency_report=consistency_report,
            )

        validity_warnings = verification.get("validity_warnings") or []

        return {
            "citation_verification": verification,
            "consistency": consistency_report,
            "trust": trust_report,
            "regeneration_attempts": 0,
            "validity_warnings": validity_warnings,
        }

    def _run_non_legal(
        self,
        query: str,
        intent: IntentResult,
        history: Optional[List[Dict[str, str]]],
        user_documents: Optional[List[Dict]] = None,
        model_id: Optional[str] = None,
    ) -> Dict:
        # 非法律文档分析（general + 携带文档）：注入文档全文 + 文档分析提示词；
        # 寒暄/普通非法律问题不注入文档，保持原样
        document_mode = intent.intent == "general_non_legal" and bool(user_documents)
        context_docs = (
            self._build_context_docs(user_documents=user_documents)
            if document_mode
            else None
        )
        system_prompt = get_system_prompt(intent.intent, document_mode=document_mode)
        response = self.model.generate(
            query,
            system_prompt=system_prompt,
            context_docs=context_docs,
            history=history,
            model_id=model_id,
        )
        trust_report = None
        return {
            "query": query,
            "answer": response,
            "use_rag": False,
            "retrieved_articles": [],
            "citation_verification": dict(_EMPTY_VERIFICATION),
            "consistency": None,
            "trust": None,
            "regeneration_attempts": 0,
            "intent": intent.to_dict(),
            "query_rewrite": None,
            "rag_used": False,
        }

    def _run_validity(
        self,
        query: str,
        intent: IntentResult,
        task: TaskDecision,
        history: Optional[List[Dict[str, str]]] = None,
        model_id: Optional[str] = None,
    ) -> Dict:
        validity = self.verifier.validity if self.verifier else LawValidityService()
        evidence = build_validity_evidence(task.law_name, validity)
        response = self.model.generate(
            query,
            system_prompt=get_system_prompt("validity_check"),
            context_docs=[evidence["text"]],
            history=history,
            model_id=model_id,
        )
        return {
            "query": query,
            "answer": response,
            "use_rag": False,
            "retrieved_articles": [],
            "citation_verification": dict(_EMPTY_VERIFICATION),
            "consistency": None,
            "trust": None,
            "regeneration_attempts": 0,
            "intent": intent.to_dict(),
            "query_rewrite": None,
            "rag_used": False,
            "task": task.to_dict(),
            "validity_evidence": evidence,
        }

    def _retrieve_articles(
        self,
        rewrite: RewriteResult,
        history: Optional[List[Dict[str, str]]],
    ) -> Tuple[List[Document], List[float], bool]:
        """Multi-query retrieval with relevance threshold."""
        min_rel = Config.RETRIEVAL_MIN_RELEVANCE
        per_query: List[List[Tuple[Document, float]]] = []

        for rq in rewrite.retrieval_queries:
            combined = self._build_retrieval_query(rq, history)
            scored = self.store.similarity_search_unique(
                combined, k=Config.TOP_K_RETRIEVAL
            )
            best: Dict[Tuple[str, str], Tuple[Document, float]] = {}
            for doc, distance in scored:
                if not is_retrieval_relevant(distance, min_rel):
                    continue
                key = article_key(doc)
                if not key[0] or not key[1]:
                    continue
                if key not in best or distance < best[key][1]:
                    best[key] = (doc, distance)
            per_query.append(sorted(best.values(), key=lambda x: x[1]))

        ranked = self._merge_query_results(per_query, Config.TOP_K_RETRIEVAL)
        if not ranked:
            return [], [], False

        docs = [doc for doc, _ in ranked]
        scores = [dist for _, dist in ranked]
        return docs, scores, True

    @staticmethod
    def _merge_query_results(
        per_query: List[List[Tuple[Document, float]]],
        k: int,
    ) -> List[Tuple[Document, float]]:
        """多查询结果合并：主查询（用户原话改写）优先，扩展查询按序补位。

        修复（2026-08-09）：「离婚冷静期是多长时间？」经扩展查询
        「离婚 夫妻共同财产 子女抚养」命中财产分割条款，相关度反而高于用户
        原话命中的冷静期条款（民法典第1077条），按相关度全局排序会把用户
        真正关心的条文挤出 top-k，导致模型「检索不到法条依据」。
        改为逐查询按序取位：主查询结果优先，扩展查询只补剩余空位，
        并按（法律名, 条号）跨查询去重。
        """
        merged: List[Tuple[Document, float]] = []
        taken = set()
        for lst in per_query:
            for doc, distance in lst:
                key = article_key(doc)
                if key in taken:
                    continue
                taken.add(key)
                merged.append((doc, distance))
                if len(merged) >= k:
                    return merged
        return merged

    @staticmethod
    def _build_context_docs(
        rag_block: str = "",
        user_documents: Optional[List[Dict]] = None,
    ) -> Optional[List[str]]:
        parts: List[str] = []
        user_block = format_user_documents(user_documents or [])
        if user_block:
            parts.append(user_block)
        if rag_block:
            parts.append(
                f"参考法条（仅可引用下列条文，引用须与「原文」一致）：\n{rag_block}"
            )
        return parts or None

    @staticmethod
    def _truncate_user_documents(
        docs: Optional[List[Dict]],
    ) -> Optional[List[Dict]]:
        if not docs:
            return None
        max_chars = Config.DOC_MAX_CONTEXT_CHARS
        total = 0
        trimmed: List[Dict] = []
        for doc in docs[: Config.DOC_MAX_ATTACHMENTS]:
            text = (doc.get("text") or "").strip()
            if not text:
                continue
            remaining = max_chars - total
            if remaining <= 0:
                break
            if len(text) > remaining:
                text = text[:remaining] + "\n…（文档内容已截断）"
            total += len(text)
            trimmed.append({**doc, "text": text})
        return trimmed or None

    @staticmethod
    def _build_generation_query(query: str, rewrite: RewriteResult) -> str:
        if rewrite.cleaned and rewrite.cleaned != query:
            return rewrite.cleaned
        return query

    @staticmethod
    def _needs_focus_regeneration(
        query: str,
        rewrite: RewriteResult,
        response: str,
    ) -> bool:
        """Detect answer focused on ID detention when user asks about dismissal."""
        dismissal_pat = r"辞退|被开除|被解雇|被裁员|违法解除|开除"

        if not re.search(dismissal_pat, query) and not re.search(
            dismissal_pat, rewrite.cleaned
        ):
            return False

        dismissal_in_answer = bool(
            re.search(r"解除|辞退|开除|裁员|经济补偿|赔偿金|仲裁", response)
        )
        id_card_focus = bool(
            re.search(r"扣押.{0,6}(身份证|证件)|居民身份证", response)
        )
        return id_card_focus and not dismissal_in_answer

    @staticmethod
    def _build_retrieval_query(
        query: str, history: Optional[List[Dict[str, str]]]
    ) -> str:
        if not history:
            return query
        recent_user = [
            m["content"] for m in history if m.get("role") == "user"
        ][-2:]
        if not recent_user:
            return query
        return " ".join(recent_user + [query])

    @staticmethod
    def _build_feedback(verification: Dict) -> str:
        lines = []
        for c in verification.get("extracted_citations", []):
            if c.get("wrong_article_mismatch"):
                lines.append(
                    f"- {c['text']}：条号与内容不符，建议改为"
                    f"《{c.get('suggested_law_name', c['law_name'])}》"
                    f"{c.get('suggested_article_num', '')}"
                )
            elif not c.get("exists"):
                lines.append(f"- {c['text']}：法条在知识库中不存在，请勿引用")
            elif (c.get("content_match_score") or 0) < Config.CONTENT_MATCH_THRESHOLD:
                lines.append(f"- {c['text']}：{c.get('verdict', '内容不匹配')}")
        if not lines:
            lines.append("- 请确保引用条文原文与参考法条完全一致")
        return "\n".join(lines)

    @staticmethod
    def _format_retrieved(
        docs: List[Document],
        scores: Optional[List[float]] = None,
    ) -> List[Dict]:
        out = []
        for i, doc in enumerate(docs):
            score = scores[i] if scores and i < len(scores) else None
            out.append(format_article_record(doc, score))
        return out
