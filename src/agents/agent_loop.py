"""工具调用循环引擎（ReAct 简化版）：生成 → 调用工具 → 再看 → 再生成。

- 上限轮次防死循环；每轮工具决策 token 上限防费用爆炸；
- 工具结果只作模型参考；最终回答照常由外层引用核验闭环检查；
- 本地引擎（NotImplementedError）自动降级为普通生成（等于现状）；
- 工具执行失败记录进轨迹并继续（不中断循环）。
"""
import json
import time
from typing import Any, Dict, Generator, List, Optional, Tuple

from langchain_core.documents import Document

from src.agents.tools import TOOLS, execute_tool
from src.agents.trace import AgentEvent, AgentStatusEvent, ToolTraceStep
from src.config import Config
from src.llm.base import ToolCall
from src.pipeline.answer_pipeline import PipelineContext


def _tool_result_payload(result: Dict) -> str:
    """工具结果转模型可见文本（截断防止上下文爆炸）。"""
    text = json.dumps(result, ensure_ascii=False)
    return text[: Config.DOC_MAX_CONTEXT_CHARS]


class AgentToolLoop:
    """一次问答的工具循环。stream()/run() 执行后，answer / trace / found_docs 即为结果。"""

    def __init__(self, model, store, validity=None, max_rounds: int = None):
        self.model = model
        self.store = store
        self.validity = validity
        self.max_rounds = max_rounds or Config.AGENT_MAX_TOOL_ROUNDS
        self.answer: str = ""
        self.trace: List[ToolTraceStep] = []
        self.found_docs: List[Document] = []

    # ------------------------------------------------------------------
    # 工具执行
    # ------------------------------------------------------------------

    def _execute_with_payload(self, step_no: int, call: ToolCall) -> Tuple[ToolTraceStep, str]:
        t0 = time.time()
        try:
            result = execute_tool(
                call.name, call.arguments,
                store=self.store, validity=self.validity,
            )
            cost_ms = int((time.time() - t0) * 1000)
            # 工具返回 error 键（如未知工具）视为执行失败，记录进轨迹但不中断循环
            ok = "error" not in result
            step = ToolTraceStep(
                step_no, call.name, call.arguments,
                self._summarize_result(result), ok, cost_ms,
            )
            if call.name == "search_articles":
                self.found_docs.extend(self._docs_from_payload(result))
            return step, _tool_result_payload(result)
        except Exception as e:  # noqa: BLE001 - 工具失败不中断循环
            cost_ms = int((time.time() - t0) * 1000)
            err = f"工具执行失败：{e}"
            step = ToolTraceStep(step_no, call.name, call.arguments, err, False, cost_ms)
            return step, json.dumps({"error": err}, ensure_ascii=False)

    @staticmethod
    def _summarize_result(result: Dict) -> str:
        if result.get("error"):
            return result["error"]
        if result.get("count") is not None:
            return f"命中 {result['count']} 条法条"
        if result.get("effective") is not None:
            if result["effective"]:
                return "现行有效"
            parts = ["已废止"]
            if result.get("repeal_date"):
                parts.append(f"（{result['repeal_date']}）")
            if result.get("superseded_by"):
                parts.append(f"，替代《{result['superseded_by']}》")
            return "".join(parts)
        return f"共 {len(result)} 个字段"

    @staticmethod
    def _docs_from_payload(payload: Dict) -> List[Document]:
        """把检索结果的 payload 还原为 Document（供引用核验合并上下文）。"""
        docs = []
        for a in payload.get("articles", []):
            meta = {k: a.get(k, "") for k in (
                "law_name", "article_num", "status", "effective_date", "repeal_date", "superseded_by"
            )}
            docs.append(Document(
                page_content=a.get("full_text") or a.get("content") or "",
                metadata=meta,
            ))
        return docs

    @staticmethod
    def _running_detail(call: ToolCall) -> str:
        if call.name == "search_articles":
            q = call.arguments.get("query", "")
            law = call.arguments.get("law_name", "")
            return f"正在检索法条：{q}" + (f"（《{law}》）" if law else "")
        if call.name == "check_law_validity":
            return f"正在核查《{call.arguments.get('law_name', '')}》的时效状态"
        return f"正在调用工具 {call.name}"

    # ------------------------------------------------------------------
    # 循环主体
    # ------------------------------------------------------------------

    def _build_messages(self, ctx: PipelineContext) -> List[Dict[str, str]]:
        return self.model.build_messages(
            ctx.generation_query,
            ctx.system_prompt,
            ctx.context_docs,
            ctx.history,
            ctx.intent_hint,
        )

    def _append_tool_round(self, messages: List[Dict[str, str]], call: ToolCall, result_text: str) -> None:
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }],
        })
        messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": result_text,
        })

    def stream(self, ctx: PipelineContext, model_id: Optional[str] = None) -> Generator[AgentEvent, None, None]:
        """流式执行：yield AgentStatusEvent（状态）或 str（最终回答文本块）。

        结束条件：模型不再调用工具（直接输出文本）或轮次耗尽。
        """
        messages = self._build_messages(ctx)
        used = 0
        for rnd in range(1, self.max_rounds + 1):
            used = rnd
            tool_calls: List[ToolCall] = []
            try:
                for kind, payload in self.model.complete_stream_with_tools(
                    messages, TOOLS, model_id=model_id,
                    max_tokens=Config.AGENT_DECISION_MAX_TOKENS,
                ):
                    if kind == "text":
                        self.answer += payload
                        yield payload
                    else:
                        tool_calls = payload
            except NotImplementedError:
                # 本地引擎不支持函数调用：退回普通生成（等于现状）
                for chunk in self.model.generate_stream_messages(messages, model_id=model_id):
                    self.answer += chunk
                    yield chunk
                return

            if not tool_calls:
                return  # 模型直接给出最终回答（文本已流式输出）

            for call in tool_calls:
                yield AgentStatusEvent(
                    step=rnd, tool_name=call.name, status="running",
                    detail=self._running_detail(call),
                )
                step, result_text = self._execute_with_payload(rnd, call)
                self.trace.append(step)
                self._append_tool_round(messages, call, result_text)
                yield AgentStatusEvent(
                    step=rnd, tool_name=call.name,
                    status="error" if not step.success else "done",
                    result_summary=step.result_summary,
                )

        # 轮次耗尽兜底：不带工具再问一次，流式输出最终回答
        yield AgentStatusEvent(
            step=used, status="generating",
            detail=f"已到达工具调用轮次上限（{self.max_rounds} 轮），综合生成最终回答…",
        )
        for chunk in self.model.generate_stream_messages(messages, model_id=model_id):
            self.answer += chunk
            yield chunk

    def run(self, ctx: PipelineContext, model_id: Optional[str] = None) -> Tuple[str, List[ToolTraceStep]]:
        """非流式版（/api/chat 同步路径）：返回 (最终回答, 轨迹)。

        复用 stream() 走同一套循环逻辑（工具轮 + 降级 + 兜底），
        只收集文本块不对外转发状态事件；答案与轨迹与流式路径完全一致。
        """
        for event in self.stream(ctx, model_id=model_id):
            pass  # stream() 内部已把文本块累积进 self.answer
        return self.answer, self.trace
