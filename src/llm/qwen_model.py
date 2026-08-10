"""模型门面（双模式：本地 Qwen2.5-7B 推理 / 多模型 API 引擎）。

懒加载 + RAG 上下文注入；对外接口 generate / generate_stream 在两种模式下一致，
调用方（answer_pipeline / self_consistency / SSE 层）无需感知 provider 差异。

阶段八改造：模型选择按请求透传（model_id 参数），由模型注册表解析；
不再依赖实例级 provider 字段决定单次请求用哪个模型。
"""
from typing import Dict, Generator, List, Optional
import threading

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, TextIteratorStreamer
from src.config import Config
from src.llm.api_client import APIClient
from src.llm.base import BaseLLMModel
from src.llm.model_registry import ModelSpec, get_api_model_list, resolve_model_spec


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
- 不得把甲条条文写在乙条条号下；不确定时声明不确定，不得编造条文。
- 遇到需要查证多部法律或「参考法条」检索不足的问题时，请调用 search_articles 工具补充检索后再作答。"""

_SYSTEM_PROMPT_GREETING = """你是法信通（LawTrust）智能助手，专注中国法律咨询。
用户正在寒暄。请简短友好地回应，并用一两句话说明你可以提供劳动合同、工伤、消费维权、婚姻家庭等法律信息参考。
不要引用法条，不要使用【结论】【法律分析】【依据法条】结构。控制在 3 句话以内。"""

_SYSTEM_PROMPT_GENERAL = """你是法信通（LawTrust）智能助手，主要提供中国法律信息参考。
当前问题与法律没有直接关系。请简短、友好地回答；若无法回答，请诚实说明。
结尾用一句话引导用户提出法律相关问题。不要编造法条，不要使用【结论】【法律分析】【依据法条】结构。"""

_SYSTEM_PROMPT_DOC_ANALYSIS = """你是法信通（LawTrust）智能助手。用户上传了文档并请求分析。
请以简洁清晰的方式总结文档内容与关键信息，并按需给出分析。

- 若文档内容涉及法律问题（如合同条款、法律风险）：按【结论】【法律分析】【依据法条】
  结构作答，仅引用与问题直接相关的法条（无法条参考时凭确知知识引用并注明需人工核对）。
- 若文档与法律无关（如技术文档、项目方案）：直接客观总结文档要点即可——不要套用
  【结论】【法律分析】【依据法条】结构，不要罗列无关法条；可在开头简要说明该文档为
  技术/非法律类文档、不涉及具体法律分析，然后总结关键内容；结尾用一句话提示用户：
  如需法律咨询，可提出具体问题或上传合同等法律文件。
- 引用文档具体内容时注明出处（如《文件名》）；不确定处诚实说明，不得编造。"""

_SYSTEM_PROMPT_CONTRACT = """你是法信通（LawTrust）智能助手，专业合同审查员。用户上传了合同/协议并请求审查。

请输出结构化风险清单，格式如下（小节标题必须保留）：

【合同风险清单】
1. ⚠️ 条款类型：<条款主题，如试用期约定>
   风险点：<该条款存在的问题或法律风险>
   法律依据：<相关法条全名与条号，仅引用「参考法条」中已有的条文>
   修改建议：<具体可操作的修改方案>

……（逐条列出；确无风险则写「未发现明显风险条款」）

【总体评价】
用 2～4 句话概括合同整体风险水平（低/中/高）与最需要关注的问题。

要求：
- 引用合同条款时须与「用户上传文档」原文一致（引号内逐字复述，不得改写）；
- 引用法条时仅引用「参考法条」，条号与法律名称须一致；
- 不编造合同中不存在的条款；不确定处如实说明。"""

_SYSTEM_PROMPT_VALIDITY = """你是法信通（LawTrust）智能助手。用户询问某部法律的时效状态（是否有效/已废止）。

回答要求：
- 核心结论必须以「法律时效注册表」提供的事实为准（废止日期、替代法律），
  不得编造、不得推测废止时间；
- 用自然语言组织结论（如：《婚姻法》已于2021年1月1日废止，相关内容由《中华人民共和国民法典》吸收），
  并补充一句实务提示（如相关事项现按民法典相应编章处理）；
- 不引用法条原文，不使用【结论】【法律分析】【依据法条】三段式结构；
- 若注册表未收录该法律，如实说明。"""

# backward-compatible alias
_SYSTEM_PROMPT = _SYSTEM_PROMPT_LEGAL


def get_system_prompt(intent: str = "legal_qa", document_mode: bool = False) -> str:
    """intent：意图路由结果；document_mode：携带用户文档且提问无法律词（文档分析
    模式）时返回文档分析专用提示词——优先于意图判断（general 分支也用文档分析
    prompt，客观总结文档；涉法文档由模型按 prompt 自判后走三段式）。"""
    if document_mode:
        return _SYSTEM_PROMPT_DOC_ANALYSIS
    if intent == "greeting":
        return _SYSTEM_PROMPT_GREETING
    if intent == "general_non_legal":
        return _SYSTEM_PROMPT_GENERAL
    if intent == "validity_check":
        return _SYSTEM_PROMPT_VALIDITY
    if intent == "contract_review":
        return _SYSTEM_PROMPT_CONTRACT
    return _SYSTEM_PROMPT_LEGAL


class QwenModel(BaseLLMModel):
    def __init__(
        self,
        model_path: str = None,
        device: str = None,
        provider: str = None,
        api_client: APIClient = None,
        model_id: Optional[str] = None,
    ):
        """provider: "api" = 百炼 API（默认走 Config.LLM_PROVIDER）| "local" = 本地推理。

        model_id: 默认模型 id（未指定时 API 模式取 Config.DEFAULT_API_MODEL）。
        注意：model_id 只决定「未显式传参时的兜底」，单次请求仍以 generate 的
        model_id 参数为准（并发请求不会互相串模型）。
        """
        self.provider = provider or Config.LLM_PROVIDER
        self.model_id = model_id
        self.model_path = model_path or Config.LLM_MODEL_PATH
        req = device or Config.LLM_DEVICE
        self.device = req if req != "cuda" or torch.cuda.is_available() else "cpu"
        self._model: Optional[AutoModelForCausalLM] = None
        self._tokenizer: Optional[AutoTokenizer] = None
        # API 模式：key 缺失会在构造时抛中文 RuntimeError（服务端 lifespan 已兜底降级）
        self._api = api_client or (APIClient() if self.provider == "api" else None)
        # 按 base_url 缓存的 API 客户端（多供应商预留；本期全部为百炼同一客户端）
        self._api_clients: Dict[str, APIClient] = {}

    # ------------------------------------------------------------------
    # 模型解析
    # ------------------------------------------------------------------

    def _resolve_model(self, model_id: Optional[str]) -> ModelSpec:
        """解析模型：显式参数 > 构造默认 > 全局默认 / 本地。未知或未启用抛 ValueError。

        本地引擎不在注册表中（"local" 仅为 provider 标识）：provider == "local" 时
        合成一个 local spec，使 generate / 工具方法能进入本地分支
        （spec.provider == "local" 是各方法本地分支的判据）。
        """
        mid = model_id or self.model_id
        if not mid:
            mid = "local" if self.provider == "local" else Config.DEFAULT_API_MODEL
        if mid == "local":
            if self.provider != "local":
                raise ValueError(f"模型「local」仅本地引擎可用（当前 provider={self.provider}）")
            return ModelSpec(
                id="local",
                display_name="本地 Qwen2.5-7B",
                provider="local",
                base_url="",
                key_env="",
                price_tier="",
                capabilities="本地 7B 推理（需 CUDA GPU）",
            )
        return resolve_model_spec(mid)

    def _get_api_client(self, spec: ModelSpec) -> APIClient:
        """按 base_url 获取/创建 API 客户端（Key 统一从 spec.key_env 环境变量读取）。"""
        if spec.base_url not in self._api_clients:
            self._api_clients[spec.base_url] = APIClient(
                base_url=spec.base_url,
                provider_label="百炼" if spec.provider == "dashscope" else spec.provider,
            )
        return self._api_clients[spec.base_url]

    # ------------------------------------------------------------------
    # BaseLLMModel 契约
    # ------------------------------------------------------------------

    @property
    def model_name(self) -> str:
        """当前默认模型的展示名（如 "Qwen3.7 Plus"）。"""
        return self._resolve_model(None).display_name

    @property
    def capabilities(self) -> Dict:
        """能力标签：是否本地 / 是否流式 / 价格档位 / 能力说明。"""
        spec = self._resolve_model(None)
        return {
            "is_local": spec.provider == "local",
            "is_streaming": True,
            "price_tier": spec.price_tier,
            "capabilities": spec.capabilities,
            "model_id": spec.id,
        }

    # ------------------------------------------------------------------
    # Lazy loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._model is not None:
            return
        if self.provider == "api":
            # API 模式不加载本地模型；_api 已在 __init__ 构造（key 缺失已抛错）
            spec = self._resolve_model(None)
            print(
                f"Using API provider: {spec.id} (base: {spec.base_url})"
                f"，可用模型：{', '.join(m.id for m in get_api_model_list())}"
            )
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

    def build_messages(
        self,
        query: str,
        system_prompt: str,
        context_docs: Optional[List[str]] = None,
        history: Optional[List[Dict[str, str]]] = None,
        intent_hint: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """公开版消息构建（generate / agent_loop 共用）。"""
        return self._build_messages(query, system_prompt, context_docs, history, intent_hint)

    def generate(
        self,
        query: str,
        system_prompt: str = None,
        temperature: float = None,
        max_new_tokens: int = None,
        context_docs: List[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        intent_hint: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> str:
        system_prompt = system_prompt or _SYSTEM_PROMPT
        temperature = temperature if temperature is not None else Config.LLM_TEMPERATURE
        max_new_tokens = max_new_tokens or Config.LLM_MAX_NEW_TOKENS

        messages = self._build_messages(
            query, system_prompt, context_docs, history, intent_hint
        )

        spec = self._resolve_model(model_id)

        # ---- API 分支：多模型 OpenAI 兼容接口（按注册表路由） ----
        if spec.provider != "local":
            return self._get_api_client(spec).complete(
                messages, model_id=spec.id, temperature=temperature, max_tokens=max_new_tokens
            )

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
        model_id: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """Yield decoded text chunks as the model generates."""
        self._load()
        system_prompt = system_prompt or _SYSTEM_PROMPT
        temperature = temperature if temperature is not None else Config.LLM_TEMPERATURE
        max_new_tokens = max_new_tokens or Config.LLM_MAX_NEW_TOKENS

        messages = self._build_messages(
            query, system_prompt, context_docs, history, intent_hint
        )

        spec = self._resolve_model(model_id)

        # ---- API 分支：多模型 OpenAI 兼容接口（流式） ----
        if spec.provider != "local":
            yield from self._get_api_client(spec).complete_stream(
                messages, model_id=spec.id, temperature=temperature, max_tokens=max_new_tokens
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

    # ------------------------------------------------------------------
    # 工具调用（function calling；仅 API 引擎，本地 7B 不支持）
    # ------------------------------------------------------------------

    def supports_tools(self, model_id: Optional[str] = None) -> bool:
        """当前模型是否支持函数调用（API 引擎支持；本地 7B 不支持）。"""
        try:
            return self._resolve_model(model_id).provider != "local"
        except ValueError:
            return False

    def complete_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        model_id: Optional[str] = None,
        max_tokens: int = 512,
    ) -> "ToolDecision":
        spec = self._resolve_model(model_id)
        if spec.provider == "local":
            raise NotImplementedError("本地引擎不支持函数调用（agent_loop 会自动降级为普通生成）")
        return self._get_api_client(spec).complete_with_tools(
            messages, tools, model_id=spec.id, max_tokens=max_tokens
        )

    def complete_stream_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        model_id: Optional[str] = None,
        max_tokens: int = 512,
    ):
        spec = self._resolve_model(model_id)
        if spec.provider == "local":
            raise NotImplementedError("本地引擎不支持函数调用（agent_loop 会自动降级为普通生成）")
        yield from self._get_api_client(spec).complete_stream_with_tools(
            messages, tools, model_id=spec.id, max_tokens=max_tokens
        )

    def generate_stream_messages(
        self,
        messages: List[Dict[str, str]],
        model_id: Optional[str] = None,
        temperature: float = None,
        max_new_tokens: int = None,
    ) -> Generator[str, None, None]:
        """按原始消息列表流式生成（工具对话历史已在 messages 中）。"""
        self._load()
        temperature = temperature if temperature is not None else Config.LLM_TEMPERATURE
        max_new_tokens = max_new_tokens or Config.LLM_MAX_NEW_TOKENS
        spec = self._resolve_model(model_id)

        if spec.provider != "local":
            yield from self._get_api_client(spec).complete_stream(
                messages, model_id=spec.id, temperature=temperature, max_tokens=max_new_tokens
            )
            return

        # 本地分支：直接对 messages 做 chat template 流式
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
