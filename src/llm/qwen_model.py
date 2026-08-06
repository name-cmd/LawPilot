"""Qwen 模型封装（双模式：本地 Qwen2.5-7B 推理 / 阿里云百炼 API）。

懒加载 + RAG 上下文注入；对外接口 generate / generate_stream 在两种模式下一致，
调用方（answer_pipeline / self_consistency / SSE 层）无需感知 provider 差异。
"""
from typing import Dict, Generator, List, Optional
import threading

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, TextIteratorStreamer
from src.config import Config
from src.llm.api_client import APIClient


_SYSTEM_PROMPT_LEGAL = """你是一名专业的中国法律助手，精通中国现行有效法律法规。
请按以下结构作答（三个小节标题必须保留）：

【结论】
用 1～3 句话直接回答用户问题，给出明确结论（含关键数字、期限、条件等）。

【法律分析】
结合问题情形说明法律逻辑：谁的权利义务、适用条件、例外情形、与相关条文的衔接。本段以分析说明为主，不要简单堆砌法条原文。

【依据法条】
仅引用与问题直接相关的条文，须写全名《法律名称》第X条；引用后用引号逐字复述该条「原文」字段中的文字。
连续引用同一部法律时，每条仍须写全法律名称。禁止引用与问题无关的法条。

其他要求：
- 优先依据用户消息中的「参考法条」作答；条号与法律名称须与参考法条一致。
- 若提供了「用户上传文档」，可结合合同/文书条款分析，并注明引用来源；官方法条仍以「参考法条」为准。
- 先识别用户核心法律诉求（如解除劳动关系、拖欠工资、工伤赔偿），围绕核心诉求作答。
- 勿因用户附带提及身份证、手机号等个人信息，就只回答证件扣押或隐私条款而忽略其主要法律问题。
- 不得把甲条条文写在乙条条号下；不确定时声明不确定，不得编造条文。"""

_SYSTEM_PROMPT_GREETING = """你是法信通（LawTrust）智能助手，专注中国法律咨询。
用户正在寒暄。请简短友好地回应，并用一两句话说明你可以提供劳动合同、工伤、消费维权、婚姻家庭等法律信息参考。
不要引用法条，不要使用【结论】【法律分析】【依据法条】结构。控制在 3 句话以内。"""

_SYSTEM_PROMPT_GENERAL = """你是法信通（LawTrust）智能助手，主要提供中国法律信息参考。
当前问题与法律没有直接关系。请简短、友好地回答；若无法回答，请诚实说明。
结尾用一句话引导用户提出法律相关问题。不要编造法条，不要使用【结论】【法律分析】【依据法条】结构。"""

# backward-compatible alias
_SYSTEM_PROMPT = _SYSTEM_PROMPT_LEGAL


def get_system_prompt(intent: str = "legal_qa") -> str:
    if intent == "greeting":
        return _SYSTEM_PROMPT_GREETING
    if intent == "general_non_legal":
        return _SYSTEM_PROMPT_GENERAL
    return _SYSTEM_PROMPT_LEGAL


class QwenModel:
    def __init__(
        self,
        model_path: str = None,
        device: str = None,
        provider: str = None,
        api_client: APIClient = None,
    ):
        """provider: "api" = 百炼 API（默认走 Config.LLM_PROVIDER）| "local" = 本地推理。"""
        self.provider = provider or Config.LLM_PROVIDER
        self.model_path = model_path or Config.LLM_MODEL_PATH
        req = device or Config.LLM_DEVICE
        self.device = req if req != "cuda" or torch.cuda.is_available() else "cpu"
        self._model: Optional[AutoModelForCausalLM] = None
        self._tokenizer: Optional[AutoTokenizer] = None
        # API 模式：key 缺失会在构造时抛中文 RuntimeError（服务端 lifespan 已兜底降级）
        self._api = api_client or (APIClient() if self.provider == "api" else None)

    # ------------------------------------------------------------------
    # Lazy loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._model is not None:
            return
        if self.provider == "api":
            # API 模式不加载本地模型；_api 已在 __init__ 构造（key 缺失已抛错）
            print(f"Using API provider: {Config.API_MODEL} (base: {Config.API_BASE_URL})")
            return
        print(f"Loading LLM from {self.model_path} …")
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, trust_remote_code=True
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            torch_dtype=torch.float16,
            device_map="auto" if self.device == "cuda" else None,
            trust_remote_code=True,
        )
        if self.device != "cuda":
            self._model = self._model.to(self.device)
        self._model.eval()

    @property
    def model(self) -> AutoModelForCausalLM:
        self._load()
        if self.provider == "api":
            raise RuntimeError(
                "API 模式下不加载本地模型，model/tokenizer 不可用"
                "（logits_entropy 等依赖本地 logits 的功能仅本地模式可用）"
            )
        return self._model

    @property
    def tokenizer(self) -> AutoTokenizer:
        self._load()
        if self.provider == "api":
            raise RuntimeError(
                "API 模式下不加载本地模型，model/tokenizer 不可用"
                "（logits_entropy 等依赖本地 logits 的功能仅本地模式可用）"
            )
        return self._tokenizer

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        query: str,
        system_prompt: str,
        context_docs: Optional[List[str]] = None,
        history: Optional[List[Dict[str, str]]] = None,
        intent_hint: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        user_content = query
        if context_docs:
            ctx = "\n\n".join(context_docs)
            user_content = f"{ctx}\n\n问题：{query}"
            if intent_hint:
                user_content += f"\n\n（{intent_hint}）"
        elif intent_hint:
            user_content = f"{intent_hint}\n\n用户问题：{query}"

        messages = [{"role": "system", "content": system_prompt}]
        for msg in (history or [])[-Config.MAX_HISTORY_MESSAGES :]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_content})
        return messages

    def generate(
        self,
        query: str,
        system_prompt: str = None,
        temperature: float = None,
        max_new_tokens: int = None,
        context_docs: List[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        intent_hint: Optional[str] = None,
    ) -> str:
        system_prompt = system_prompt or _SYSTEM_PROMPT
        temperature = temperature if temperature is not None else Config.LLM_TEMPERATURE
        max_new_tokens = max_new_tokens or Config.LLM_MAX_NEW_TOKENS

        messages = self._build_messages(
            query, system_prompt, context_docs, history, intent_hint
        )

        # ---- API 分支：百炼 OpenAI 兼容接口 ----
        if self.provider == "api":
            return self._api.complete(messages, temperature=temperature, max_tokens=max_new_tokens)

        # ---- 本地分支：transformers 推理 ----
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)

        with torch.no_grad():
            out_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                do_sample=temperature > 0,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        new_ids = out_ids[0][inputs.input_ids.shape[1]:]
        return self.tokenizer.decode(new_ids, skip_special_tokens=True)

    def generate_stream(
        self,
        query: str,
        system_prompt: str = None,
        temperature: float = None,
        max_new_tokens: int = None,
        context_docs: List[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        intent_hint: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """Yield decoded text chunks as the model generates."""
        self._load()
        system_prompt = system_prompt or _SYSTEM_PROMPT
        temperature = temperature if temperature is not None else Config.LLM_TEMPERATURE
        max_new_tokens = max_new_tokens or Config.LLM_MAX_NEW_TOKENS

        messages = self._build_messages(
            query, system_prompt, context_docs, history, intent_hint
        )

        # ---- API 分支：百炼 OpenAI 兼容接口（流式） ----
        if self.provider == "api":
            yield from self._api.complete_stream(
                messages, temperature=temperature, max_tokens=max_new_tokens
            )
            return

        # ---- 本地分支：transformers 流式推理 ----
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)

        streamer = TextIteratorStreamer(
            self.tokenizer, skip_prompt=True, skip_special_tokens=True
        )
        gen_kwargs = dict(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            do_sample=temperature > 0,
            pad_token_id=self.tokenizer.eos_token_id,
            streamer=streamer,
        )

        thread = threading.Thread(target=self.model.generate, kwargs=gen_kwargs)
        thread.start()
        for chunk in streamer:
            if chunk:
                yield chunk
        thread.join()
