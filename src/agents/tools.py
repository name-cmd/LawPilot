"""法律工具注册表：工具的「说明书」（模型用）与「执行者」（代码用）。

首期 2 个确定性工具：检索法条、查询法律时效。
工具执行只触碰本地向量库与本地注册表，无任何外部调用；
未知工具/参数异常返回错误结果（不抛出——结果进入轨迹，模型可自行纠正）。
"""
import re
from typing import Any, Dict, List, Optional

from src.config import Config
from src.knowledge_base.law_validity import LawValidityService
from src.knowledge_base.retrieval_utils import format_article_record
from src.pipeline.query_rewriter import is_retrieval_relevant


SEARCH_ARTICLES_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_articles",
        "description": "在法律知识库中检索相关法条。当现有参考法条可能未覆盖问题的全部关键条文"
                       "（如问题涉及多部法律、多个条款）时调用；指定法律名称可提高精度。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索词，描述要查找的法律问题，如：工伤认定时效"},
                "law_name": {"type": "string", "description": "可选，指定法律名称，如：工伤保险条例"},
            },
            "required": ["query"],
        },
    },
}

CHECK_VALIDITY_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "check_law_validity",
        "description": "查询某部法律是否现行有效（含废止日期与替代法律）。"
                       "当回答涉及特定法律的时效状态、或引用的法律可能已废止时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "law_name": {"type": "string", "description": "法律名称，如：婚姻法"},
            },
            "required": ["law_name"],
        },
    },
}

TOOLS: List[Dict[str, Any]] = [SEARCH_ARTICLES_TOOL, CHECK_VALIDITY_TOOL]


def _clean_arg(value: Any) -> str:
    """参数清洗：去首尾空白、剔除控制字符、截断超长。"""
    text = str(value or "").strip()
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)
    return text[: Config.AGENT_TOOL_ARG_MAX_LEN]


def _execute_search_articles(args: Dict[str, Any], store) -> Dict:
    """向量检索执行者。store 只需提供 similarity_search_unique（测试可注入假 store）。"""
    query = _clean_arg(args.get("query"))
    if not query:
        return {"articles": [], "count": 0, "note": "检索词为空"}
    raw = store.similarity_search_unique(query, k=Config.TOP_K_RETRIEVAL)
    hits = []
    for doc, distance in raw:
        if not is_retrieval_relevant(distance, Config.RETRIEVAL_MIN_RELEVANCE):
            continue
        hits.append(format_article_record(doc, distance))
    return {"articles": hits, "count": len(hits), "note": ""}


def _execute_check_law_validity(args: Dict[str, Any], validity: LawValidityService) -> Dict:
    law_name = _clean_arg(args.get("law_name"))
    if not law_name:
        return {"effective": True, "status": "effective", "note": "法律名称为空"}
    result = validity.check_citation(law_name, "")
    return {**result.to_dict(), "note": ""}


def execute_tool(
    name: str,
    args: Dict[str, Any],
    store=None,
    validity: Optional[LawValidityService] = None,
) -> Dict:
    """统一分发入口：未知工具返回错误结果（不抛出，进入轨迹）。"""
    if name == "search_articles":
        return _execute_search_articles(args or {}, store)
    if name == "check_law_validity":
        return _execute_check_law_validity(args or {}, validity or LawValidityService())
    return {"error": f"未知工具：{name}"}
