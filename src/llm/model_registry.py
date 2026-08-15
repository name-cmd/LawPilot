"""模型注册表：所有可用模型（API 引擎）的单一数据源 + 离线引擎就绪检测。

新增模型 = 在 MODEL_REGISTRY 加一行，前端模型选择器（/api/models）自动出现新选项。

本期 7 个模型全部托管在阿里云百炼（共用 DASHSCOPE_API_KEY），但每个条目独立存放
base_url / key_env 字段，为后期接入其他平台（DeepSeek / Moonshot / 智谱原厂）预留：
届时仅需改对应条目的 base_url 与 key_env，并在 .env 配置该供应商的 API Key。
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from src.config import Config


@dataclass(frozen=True)
class ModelSpec:
    """单个模型条目：id 为请求体 model 字段与 API model 参数的唯一标识。"""

    id: str
    display_name: str            # 前端展示名
    provider: str                # 供应商标识："dashscope"（本期全部）| "local" | 未来扩展
    base_url: str                # OpenAI 兼容接口地址
    key_env: str                 # API Key 来源环境变量名（绝不硬编码 key）
    price_tier: str              # 价格档位文案（展示用，估算值，以百炼控制台实际计费为准）
    capabilities: str            # 能力说明（展示用 tooltip）
    is_default: bool = False     # 是否全局默认（Auto 跟随；仅允许一个 True）
    is_enabled: bool = True      # 验证通过才启用；False 时前端隐藏/标注
    # 是否支持 enable_thinking 参数。已实测：百炼托管的全系列模型均支持该参数
    # （enable_thinking=False 关闭思考 → 输出更快、token 更省）；若有模型不支持，
    # APIClient 会按模型记忆该参数自动降级，无需改注册表
    thinking_supported: bool = True


_DASHSCOPE_BASE = Config.API_BASE_URL
_DASHSCOPE_KEY = Config.API_KEY_ENV  # "DASHSCOPE_API_KEY"

MODEL_REGISTRY: Dict[str, ModelSpec] = {
    "qwen3.7-plus": ModelSpec(
        id="qwen3.7-plus",
        display_name="Qwen3.7 Plus",
        provider="dashscope",
        base_url=_DASHSCOPE_BASE,
        key_env=_DASHSCOPE_KEY,
        price_tier="性价比档（约 2~4 元/百万 token，新用户含百万级免费额度）",
        capabilities="256K 超长上下文，综合均衡，默认推荐",
        is_default=True,
        thinking_supported=True,
    ),
    "qwen-turbo": ModelSpec(
        id="qwen-turbo",
        display_name="Qwen Turbo",
        provider="dashscope",
        base_url=_DASHSCOPE_BASE,
        key_env=_DASHSCOPE_KEY,
        price_tier="轻量档（约 1~2 元/百万 token）",
        capabilities="极速低延迟，适合日常高频咨询",
        thinking_supported=True,
    ),
    "qwen3.7-max": ModelSpec(
        id="qwen3.7-max",
        display_name="Qwen3.7 Max",
        provider="dashscope",
        base_url=_DASHSCOPE_BASE,
        key_env=_DASHSCOPE_KEY,
        price_tier="旗舰档（约 20~60 元/百万 token）",
        capabilities="复杂法律分析、长文深度推理，效果最佳",
        thinking_supported=True,
    ),
    "deepseek-v4-flash-0731": ModelSpec(
        id="deepseek-v4-flash-0731",
        display_name="DeepSeek V4 Flash",
        provider="dashscope",
        base_url=_DASHSCOPE_BASE,
        key_env=_DASHSCOPE_KEY,
        price_tier="轻量档（约 1~2 元/百万 token）",
        capabilities="高速低成本，DeepSeek 系列轻量模型",
    ),
    "deepseek-v4-pro": ModelSpec(
        id="deepseek-v4-pro",
        display_name="DeepSeek V4 Pro",
        provider="dashscope",
        base_url=_DASHSCOPE_BASE,
        key_env=_DASHSCOPE_KEY,
        price_tier="中高档（约 8~20 元/百万 token）",
        capabilities="深度推理，长文分析与多步论证",
    ),
    "kimi-k2.6": ModelSpec(
        id="kimi-k2.6",
        display_name="Kimi K2.6",
        provider="dashscope",
        base_url=_DASHSCOPE_BASE,
        key_env=_DASHSCOPE_KEY,
        price_tier="中高档（约 10~30 元/百万 token）",
        capabilities="超长上下文，多轮对话与文档分析",
    ),
    "glm-5.2": ModelSpec(
        id="glm-5.2",
        display_name="GLM 5.2",
        provider="dashscope",
        base_url=_DASHSCOPE_BASE,
        key_env=_DASHSCOPE_KEY,
        price_tier="中档（约 5~15 元/百万 token）",
        capabilities="智谱旗舰，中文理解能力强",
    ),
}


def resolve_model_spec(model_id: str) -> ModelSpec:
    """按 id 查注册表；未知或未启用时抛 ValueError（中文提示，由调用方转 HTTP 400）。"""
    spec = MODEL_REGISTRY.get(model_id)
    if spec is None:
        raise ValueError(
            f"未知模型「{model_id}」，可选：{', '.join(get_api_model_ids())}"
        )
    if not spec.is_enabled:
        raise ValueError(f"模型「{model_id}」当前未启用，请联系管理员开通。")
    return spec


def get_api_model_ids() -> List[str]:
    """返回启用中的模型 id 列表（按注册表顺序）。"""
    return [m.id for m in MODEL_REGISTRY.values() if m.is_enabled]


def get_api_model_list() -> List[ModelSpec]:
    """返回启用中的模型条目列表（/api/models 用）。"""
    return [m for m in MODEL_REGISTRY.values() if m.is_enabled]


def check_local_engine_ready() -> Dict:
    """离线引擎（本地 Qwen2.5-7B）就绪检测：CUDA GPU 可用 + 模型目录存在且非空。

    安全降级：纯 API 环境（无 torch 或未装 GPU 版）也能正常返回 reason，不崩溃。
    """
    reason = ""
    try:
        import torch  # 懒导入：API 模式不加载 torch 相关依赖

        if not torch.cuda.is_available():
            reason = "未检测到可用 CUDA GPU"
    except ImportError:
        reason = "当前环境未安装 CUDA 版 PyTorch（torch 为 CPU 版）"

    if not reason:
        model_dir = Path(Config.LLM_MODEL_PATH)
        if not model_dir.is_dir():
            reason = f"本地模型目录不存在：{model_dir}"
        elif not any(model_dir.iterdir()):
            reason = f"本地模型目录为空：{model_dir}"

    return {"available": not reason, "reason": reason}
