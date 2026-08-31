"""OpenAI 兼容 API 客户端（多模型注册表驱动），含重试/超时/流式解析。

与本地 QwenModel 解耦：本模块不依赖 torch / transformers。
消息结构由 QwenModel._build_messages() 统一构建后传入（避免两处重复）。

阶段八改造：模型改按请求传递（model_id），不再绑定单一模型；
模型条目（base_url / key_env / 能力）统一由 src/llm/model_registry.py 管理。
"""
import json
import os
import random
import time
from typing import Dict, Generator, List, Optional, Set

from openai import (
    OpenAI,
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    BadRequestError,
)
from src.config import Config
from src.llm.model_registry import resolve_model_spec

# 网络/服务端类错误：可重试
_RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


class APIClient:
    """OpenAI 兼容接口封装：非流式/流式补全 + 统一重试与错误分类。

    使用方式：
        client = APIClient()
        text = client.complete(messages, model_id="qwen3.7-plus", temperature=0.4, max_tokens=1024)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        provider_label: str = "百炼",
    ):
        # api_key 可覆盖：后期前端传入用户自己的 Key 时用（本期一律读环境变量）
        api_key = api_key or os.environ.get(Config.API_KEY_ENV)
        if not api_key:
            raise RuntimeError(
                f"未配置 {Config.API_KEY_ENV} 环境变量（或在项目根目录 .env 中设置），"
                "请到阿里云百炼控制台获取 API Key。"
            )
        self.base_url = base_url or Config.API_BASE_URL
        self.api_key = api_key
        # 错误提示中的平台名（默认"百炼"；接其他平台时传入对应名称）
        self.provider_label = provider_label
        self._client: Optional[OpenAI] = None
        # enable_thinking 参数开关（仅当非 None 时传给 API；遇 400 报错自动去掉以兼容旧模型）
        self._enable_thinking = Config.API_ENABLE_THINKING
        # 已确认不支持 enable_thinking 的模型 id 集合（按模型记忆，互不影响）
        self._thinking_unsupported: Set[str] = set()

    def _get_client(self) -> OpenAI:
        """懒创建 OpenAI 客户端（SDK 自带重试置 0，由本类统一控制重试策略）。"""
        if self._client is None:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=Config.API_TIMEOUT_SECONDS,
                max_retries=0,
            )
        return self._client

    def _should_send_thinking(self, model_id: str) -> bool:
        """是否发送 enable_thinking 参数：全局开关开 + 该模型未被 400 降级过 + 注册表支持。"""
        if self._enable_thinking is None:
            return False
        if model_id in self._thinking_unsupported:
            return False
        try:
            return resolve_model_spec(model_id).thinking_supported
        except ValueError:
            return False

    def _request_kwargs(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> Dict:
        """组装请求参数；temperature / max_tokens 夹取到 API 支持范围。"""
        temperature = max(0.0, min(2.0, float(temperature)))
        max_tokens = max(1, min(8192, int(max_tokens)))
        kwargs = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if self._should_send_thinking(model_id):
            kwargs["extra_body"] = {"enable_thinking": self._enable_thinking}
        return kwargs

    def _friendly_error(self, model_id: str, exc: Exception) -> str:
        """把常见 API 异常转成可操作的中文提示。"""
        if isinstance(exc, AuthenticationError):
            return f"API Key 无效或已过期，请检查 {Config.API_KEY_ENV} 是否正确（控制台：阿里云百炼 → API-KEY 管理）。"
        if isinstance(exc, PermissionDeniedError):
            return f"API Key 无权限访问模型 {model_id}，请到百炼控制台确认已开通。"
        if isinstance(exc, NotFoundError):
            return f"模型 {model_id} 未开通或模型名错误，请到百炼控制台确认（可能需先开通/领取免费额度）。"
        return str(exc)

    def _sleep_backoff(self, attempt: int) -> None:
        """指数退避 + 随机抖动，避免重试风暴。"""
        delay = Config.API_RETRY_BACKOFF_SECONDS * (2 ** attempt) + random.uniform(0, 0.5)
        time.sleep(delay)

    def _handle_call_exception(self, exc: Exception, model_id: str) -> bool:
        """统一异常分类。返回 True 表示可重试（调用方决定是否继续）。"""
        if isinstance(exc, (AuthenticationError, PermissionDeniedError, NotFoundError)):
            raise RuntimeError(
                f"{self.provider_label} API 调用失败：{self._friendly_error(model_id, exc)}"
            )
        if isinstance(exc, BadRequestError):
            # enable_thinking 兼容：模型不支持该参数时记入集合，去掉后重试一次
            if self._enable_thinking is not None and "enable_thinking" in str(exc.message):
                print(f"模型 {model_id} 不支持 enable_thinking 参数，已自动去掉后重试…")
                self._thinking_unsupported.add(model_id)
                return True
            raise RuntimeError(
                f"{self.provider_label} API 参数错误：{self._friendly_error(model_id, exc)}"
            )
        if isinstance(exc, _RETRYABLE_ERRORS):
            return True
        raise RuntimeError(
            f"{self.provider_label} API 调用失败：{self._friendly_error(model_id, exc)}"
        )

    def _log_usage(self, model_id: str, response) -> None:
        """打印 token 用量（阶段四成本数据的来源），并追加落盘 usage_log.jsonl。

        落盘文件：data/benchmark/usage_log.jsonl（每行一条 JSON），
        供 run_legal_trust_benchmark.py 聚合 D 组成本指标；写盘失败不影响主流程。
        """
        if not Config.API_LOG_USAGE:
            return
        usage = getattr(response, "usage", None)
        if not usage:
            return
        print(
            f"[API 用量] {model_id}: prompt={usage.prompt_tokens} "
            f"completion={usage.completion_tokens} total={usage.total_tokens}"
        )
        try:
            from pathlib import Path

            rec = {
                "ts": time.time(),
                "model": model_id,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
            path = Path(Config.BASE_DIR) / "data" / "benchmark" / "usage_log.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 非流式
    # ------------------------------------------------------------------

    def complete(
        self,
        messages: List[Dict[str, str]],
        model_id: str,
        temperature: float = Config.LLM_TEMPERATURE,
        max_tokens: int = Config.LLM_MAX_NEW_TOKENS,
    ) -> str:
        kwargs = self._request_kwargs(
            model_id, messages, temperature, max_tokens, stream=False
        )

        last_exc = None
        for attempt in range(Config.API_MAX_RETRIES + 1):
            try:
                resp = self._get_client().chat.completions.create(**kwargs)
                self._log_usage(model_id, resp)
                return resp.choices[0].message.content or ""
            except Exception as exc:  # noqa: BLE001 - 统一分类
                last_exc = exc
                retryable = self._handle_call_exception(exc, model_id)  # 不可重试的异常在此直接抛出
                if retryable and attempt < Config.API_MAX_RETRIES:
                    print(
                        f"{self.provider_label} API 调用失败（{type(exc).__name__}），"
                        f"{Config.API_MAX_RETRIES - attempt} 秒后重试…"
                    )
                    self._sleep_backoff(attempt)
                elif not retryable:
                    break
        raise RuntimeError(
            f"{self.provider_label} API 调用失败（已重试 {Config.API_MAX_RETRIES} 次）："
            f"{self._friendly_error(model_id, last_exc)}"
        )

    # ------------------------------------------------------------------
    # 流式
    # ------------------------------------------------------------------

    def complete_stream(
        self,
        messages: List[Dict[str, str]],
        model_id: str,
        temperature: float = Config.LLM_TEMPERATURE,
        max_tokens: int = Config.LLM_MAX_NEW_TOKENS,
    ) -> Generator[str, None, None]:
        """逐段 yield 文本内容；思考链 reasoning_content 一律跳过不输出。

        重试语义：仅「第一个 chunk 产出前」的失败才重试整个流（总重试次数有上限）；
        一旦 yield 过内容，后续异常立即上抛——防止前端收到重复/截断拼接的内容。
        """
        kwargs = self._request_kwargs(
            model_id, messages, temperature, max_tokens, stream=True
        )
        produced = False  # 是否已产出过内容
        last_exc = None
        attempts = 0

        while True:
            attempts += 1
            try:
                stream = self._get_client().chat.completions.create(**kwargs)
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta is None:
                        continue
                    if getattr(delta, "reasoning_content", None):
                        continue  # 思考链不属于回答内容，跳过
                    if delta.content:
                        produced = True
                        yield delta.content
                return  # 正常流式结束
            except Exception as exc:  # noqa: BLE001 - 统一分类
                last_exc = exc
                retryable = self._handle_call_exception(exc, model_id)  # 不可重试的异常在此直接抛出
                if produced or attempts > Config.API_MAX_RETRIES or not retryable:
                    raise RuntimeError(
                        f"{self.provider_label} API 流式调用失败"
                        f"{'（已产出部分内容，停止重试）' if produced else f'（已重试 {Config.API_MAX_RETRIES} 次）'}"
                        f"：{self._friendly_error(model_id, exc)}"
                    )
                print(f"{self.provider_label} API 流式请求失败（{type(exc).__name__}），准备重试…")
                self._sleep_backoff(attempts - 1)

    # ------------------------------------------------------------------
    # 工具调用（function calling）
    # ------------------------------------------------------------------

    def complete_with_tools(
        self,
        messages,
        tools,
        model_id: str,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> "ToolDecision":
        """非流式工具决策。temperature 固定 0.0：决策要稳定可复现。

        重试语义与 complete 一致：可重试错误（网络/限流/5xx）自动退避重试，
        认证/参数类错误立即抛出（中文包装）。
        """
        from src.llm.base import ToolCall, ToolDecision

        kwargs = self._request_kwargs(model_id, messages, temperature, max_tokens, stream=False)
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

        last_exc = None
        for attempt in range(Config.API_MAX_RETRIES + 1):
            try:
                resp = self._get_client().chat.completions.create(**kwargs)
                self._log_usage(model_id, resp)
                msg = resp.choices[0].message
                if not getattr(msg, "tool_calls", None):
                    return ToolDecision(text=msg.content or "", tool_calls=[])
                calls = []
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    calls.append(ToolCall(
                        id=tc.id or "",
                        name=tc.function.name or "",
                        arguments=args if isinstance(args, dict) else {},
                    ))
                return ToolDecision(text="", tool_calls=calls)
            except Exception as exc:  # noqa: BLE001 - 统一分类
                last_exc = exc
                retryable = self._handle_call_exception(exc, model_id)  # 不可重试的异常在此直接抛出
                if retryable and attempt < Config.API_MAX_RETRIES:
                    print(
                        f"{self.provider_label} API 工具调用失败（{type(exc).__name__}），"
                        f"{Config.API_MAX_RETRIES - attempt} 秒后重试…"
                    )
                    self._sleep_backoff(attempt)
                elif not retryable:
                    break
        raise RuntimeError(
            f"{self.provider_label} API 工具调用失败（已重试 {Config.API_MAX_RETRIES} 次）："
            f"{self._friendly_error(model_id, last_exc)}"
        )

    def complete_stream_with_tools(
        self,
        messages,
        tools,
        model_id: str,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ):
        """流式工具决策：yield ("text", str)；流内含工具调用时结束前再 yield ("tool_calls", [...]).

        重试语义与 complete_stream 一致：首个产出前的失败才重试；
        已产出内容后异常立即上抛。
        """
        from src.llm.base import ToolCall

        kwargs = self._request_kwargs(model_id, messages, temperature, max_tokens, stream=True)
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
        produced = False
        last_exc = None
        attempts = 0

        while True:
            attempts += 1
            try:
                stream = self._get_client().chat.completions.create(**kwargs)
                acc: dict = {}
                has_tool_calls = False
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta is None:
                        continue
                    if getattr(delta, "reasoning_content", None):
                        continue  # 思考链不属于回答内容，跳过
                    if delta.content:
                        produced = True
                        yield ("text", delta.content)
                    if delta.tool_calls:
                        has_tool_calls = True
                        for tc in delta.tool_calls:
                            idx = tc.index
                            entry = acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                            if tc.id:
                                entry["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    entry["name"] += tc.function.name
                                if tc.function.arguments:
                                    entry["arguments"] += tc.function.arguments
                if has_tool_calls:
                    calls = []
                    for idx in sorted(acc):
                        entry = acc[idx]
                        try:
                            args = json.loads(entry["arguments"] or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        calls.append(ToolCall(
                            id=entry["id"],
                            name=entry["name"],
                            arguments=args if isinstance(args, dict) else {},
                        ))
                    yield ("tool_calls", calls)
                return
            except Exception as exc:  # noqa: BLE001 - 统一分类，与 complete_stream 一致
                last_exc = exc
                retryable = self._handle_call_exception(exc, model_id)
                if produced or attempts > Config.API_MAX_RETRIES or not retryable:
                    raise RuntimeError(
                        f"{self.provider_label} API 流式工具调用失败"
                        f"{'（已产出部分内容，停止重试）' if produced else f'（已重试 {Config.API_MAX_RETRIES} 次）'}"
                        f"：{self._friendly_error(model_id, exc)}"
                    )
                print(f"{self.provider_label} API 流式工具调用失败（{type(exc).__name__}），准备重试…")
                self._sleep_backoff(attempts - 1)
