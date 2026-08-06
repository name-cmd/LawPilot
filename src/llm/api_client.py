"""OpenAI 兼容 API 客户端（阿里云百炼 DashScope），含重试/超时/流式解析。

与本地 QwenModel 解耦：本模块不依赖 torch / transformers。
消息结构由 QwenModel._build_messages() 统一构建后传入（避免两处重复）。
"""
import os
import random
import time
from typing import Dict, Generator, List, Optional

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

# 网络/服务端类错误：可重试
_RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


class APIClient:
    """百炼 OpenAI 兼容接口封装：非流式/流式补全 + 统一重试与错误分类。

    使用方式：
        client = APIClient()
        text = client.complete(messages, temperature=0.4, max_tokens=1024)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        api_key = api_key or os.environ.get(Config.API_KEY_ENV)
        if not api_key:
            raise RuntimeError(
                f"未配置 {Config.API_KEY_ENV} 环境变量（或在项目根目录 .env 中设置），"
                "请到阿里云百炼控制台获取 API Key。"
            )
        self.model_name = model_name or Config.API_MODEL
        self.base_url = base_url or Config.API_BASE_URL
        self.api_key = api_key
        self._client: Optional[OpenAI] = None
        # enable_thinking 参数开关（仅当非 None 时传给 API；遇 400 报错自动去掉以兼容旧模型）
        self._enable_thinking = Config.API_ENABLE_THINKING

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

    def _request_kwargs(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> Dict:
        """组装请求参数；temperature / max_tokens 夹取到 API 支持范围。"""
        temperature = max(0.0, min(2.0, float(temperature)))
        max_tokens = max(1, min(8192, int(max_tokens)))
        kwargs = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if self._enable_thinking is not None:
            kwargs["extra_body"] = {"enable_thinking": self._enable_thinking}
        return kwargs

    def _friendly_error(self, exc: Exception) -> str:
        """把常见 API 异常转成可操作的中文提示。"""
        if isinstance(exc, AuthenticationError):
            return f"API Key 无效或已过期，请检查 {Config.API_KEY_ENV} 是否正确（控制台：阿里云百炼 → API-KEY 管理）。"
        if isinstance(exc, PermissionDeniedError):
            return f"API Key 无权限访问模型 {self.model_name}，请到百炼控制台确认已开通。"
        if isinstance(exc, NotFoundError):
            return f"模型 {self.model_name} 未开通或模型名错误，请到百炼控制台确认（可能需先开通/领取免费额度）。"
        return str(exc)

    def _sleep_backoff(self, attempt: int) -> None:
        """指数退避 + 随机抖动，避免重试风暴。"""
        delay = Config.API_RETRY_BACKOFF_SECONDS * (2 ** attempt) + random.uniform(0, 0.5)
        time.sleep(delay)

    def _handle_call_exception(self, exc: Exception) -> bool:
        """统一异常分类。返回 True 表示可重试（调用方决定是否继续）。"""
        if isinstance(exc, (AuthenticationError, PermissionDeniedError, NotFoundError)):
            raise RuntimeError(f"百炼 API 调用失败：{self._friendly_error(exc)}")
        if isinstance(exc, BadRequestError):
            # enable_thinking 兼容：模型不支持该参数时去掉后重试一次
            if self._enable_thinking is not None and "enable_thinking" in str(exc.message):
                print("模型不支持 enable_thinking 参数，已自动去掉后重试…")
                self._enable_thinking = None
                return True
            raise RuntimeError(f"百炼 API 参数错误：{self._friendly_error(exc)}")
        if isinstance(exc, _RETRYABLE_ERRORS):
            return True
        raise RuntimeError(f"百炼 API 调用失败：{self._friendly_error(exc)}")

    def _log_usage(self, response) -> None:
        """打印 token 用量（阶段四成本数据的来源）。"""
        if Config.API_LOG_USAGE:
            usage = getattr(response, "usage", None)
            if usage:
                print(
                    f"[API 用量] {self.model_name}: prompt={usage.prompt_tokens} "
                    f"completion={usage.completion_tokens} total={usage.total_tokens}"
                )

    # ------------------------------------------------------------------
    # 非流式
    # ------------------------------------------------------------------

    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = Config.LLM_TEMPERATURE,
        max_tokens: int = Config.LLM_MAX_NEW_TOKENS,
    ) -> str:
        kwargs = self._request_kwargs(messages, temperature, max_tokens, stream=False)

        last_exc = None
        for attempt in range(Config.API_MAX_RETRIES + 1):
            try:
                resp = self._get_client().chat.completions.create(**kwargs)
                self._log_usage(resp)
                return resp.choices[0].message.content or ""
            except Exception as exc:  # noqa: BLE001 - 统一分类
                last_exc = exc
                self._handle_call_exception(exc)  # 不可重试的异常在此直接抛出
                if attempt < Config.API_MAX_RETRIES:
                    print(
                        f"百炼 API 调用失败（{type(exc).__name__}），"
                        f"{Config.API_MAX_RETRIES - attempt} 秒后重试…"
                    )
                    self._sleep_backoff(attempt)
        raise RuntimeError(
            f"百炼 API 调用失败（已重试 {Config.API_MAX_RETRIES} 次）：{self._friendly_error(last_exc)}"
        )

    # ------------------------------------------------------------------
    # 流式
    # ------------------------------------------------------------------

    def complete_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = Config.LLM_TEMPERATURE,
        max_tokens: int = Config.LLM_MAX_NEW_TOKENS,
    ) -> Generator[str, None, None]:
        """逐段 yield 文本内容；思考链 reasoning_content 一律跳过不输出。

        重试语义：仅「第一个 chunk 产出前」的失败才重试整个流（总重试次数有上限）；
        一旦 yield 过内容，后续异常立即上抛——防止前端收到重复/截断拼接的内容。
        """
        kwargs = self._request_kwargs(messages, temperature, max_tokens, stream=True)
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
                self._handle_call_exception(exc)  # 不可重试的异常在此直接抛出
                if produced or attempts > Config.API_MAX_RETRIES:
                    raise RuntimeError(
                        f"百炼 API 流式调用失败"
                        f"{'（已产出部分内容，停止重试）' if produced else f'（已重试 {Config.API_MAX_RETRIES} 次）'}"
                        f"：{self._friendly_error(exc)}"
                    )
                print(f"百炼 API 流式请求失败（{type(exc).__name__}），准备重试…")
                self._sleep_backoff(attempts - 1)
