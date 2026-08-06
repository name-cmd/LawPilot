"""
End-to-end demo of LawTrust (法信通) Chinese Legal AI system.

Usage:
    python scripts/demo.py
    python scripts/demo.py --query "醉酒驾车会受到什么处罚？"
    python scripts/demo.py --no-nli
"""
import sys
import argparse
from pathlib import Path
from typing import List, Optional

# Windows cmd 默认 GBK 终端无法打印 ✓/✗ 等 Unicode 字符，统一按 UTF-8 输出（errors=replace 兜底）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass  # Python < 3.7 无 reconfigure，忽略

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.knowledge_base.embedder import LawEmbedder
from src.knowledge_base.vector_store import LawVectorStore
from src.llm.qwen_model import QwenModel
from src.citation_verifier.citation_verifier import CitationVerifier
from src.uncertainty.self_consistency import SelfConsistencyChecker
from src.pipeline.answer_pipeline import AnswerPipeline
from src.trust_eval.legal_trust_scorer import LegalTrustScorer

INLINE_QUERY: Optional[str] = (
    "房屋租赁合同中，房东能随意涨租吗？"
)

DEMO_QUERIES = [
    "醉酒驾车会受到什么处罚？",
    "合同违约的损失赔偿如何计算？",
    "劳动合同解除需要提前多少天通知？",
    "房屋租赁合同中，房东能随意涨租吗？",
]


def print_result(result: dict, n_samples: int) -> None:
    sep = "=" * 64
    print(f"\n{sep}")
    print(f"问题：{result['query']}")
    print(sep)

    print("\n【检索到的相关法条】（已去重，显示完整正文）")
    for i, a in enumerate(result.get("retrieved_articles", []), 1):
        rel = a.get("relevance_score")
        rel_txt = f"  相关度 {rel:.0%}" if rel is not None else ""
        print(f"  {i}. 《{a.get('law_name')}》{a.get('article_num')}{rel_txt}")
        print(f"     {a.get('content', '')}")

    print("\n【模型回答】")
    print(result["answer"])

    cv = result.get("citation_verification", {})
    print("\n【法条引用核验】")
    print(cv.get("summary", ""))
    for c in cv.get("extracted_citations", []):
        print(f"  · {c.get('text')}: {c.get('verdict')}")
        if c.get("quoted_text"):
            print(f"    引用摘录: {c['quoted_text'][:80]}…" if len(c.get("quoted_text", "")) > 80 else f"    引用摘录: {c.get('quoted_text')}")

    trust = result.get("trust")
    if trust:
        print("\n【六维可信评估】")
        print(f"  说明: {trust.get('framework_note', '')}")
        for d in trust.get("dimension_details", []):
            print(f"  {d['label']}: {d['score']:.1f}  （{d.get('method', '')}）")
            for ev in d.get("evidence", [])[:2]:
                print(f"    - {ev}")
        print(f"  综合可信指数: {trust['overall_score']:.1f} ({trust['trust_level']})")
        print(f"  {trust['advice']}")

    if result.get("regeneration_attempts"):
        print(f"\n  （已自动修正 {result['regeneration_attempts']} 次）")


def resolve_queries(cli_query: Optional[str]) -> List[str]:
    if cli_query:
        return [cli_query]
    if INLINE_QUERY:
        return [INLINE_QUERY]
    return DEMO_QUERIES


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default=None)
    parser.add_argument("--db-dir", default=Config.LAW_DB_DIR)
    parser.add_argument("--n-samples", type=int, default=3)
    parser.add_argument("--no-nli", action="store_true")
    parser.add_argument("--no-rag", action="store_true")
    parser.add_argument("--consistency", action="store_true")
    args = parser.parse_args()

    print("=== 法信通 LawTrust Demo ===")
    print("正在加载模型，请稍候 …\n")

    embedder = LawEmbedder()
    store = LawVectorStore(persist_directory=args.db_dir, embedder=embedder)
    store.load()

    model = QwenModel()
    verifier = CitationVerifier(
        vector_store=store,
        embedder=embedder,
        enable_nli=not args.no_nli,
    )
    consistency = SelfConsistencyChecker(model=model, embedder=embedder)
    pipeline = AnswerPipeline(
        store=store,
        model=model,
        verifier=verifier,
        consistency=consistency,
        trust_scorer=LegalTrustScorer(),
    )

    for q in resolve_queries(args.query):
        result = pipeline.run(
            q,
            use_rag=not args.no_rag,
            enable_consistency=args.consistency,
            n_consistency_samples=args.n_samples,
        )
        print_result(result, args.n_samples)

    print("\n=== Demo 结束 ===")


if __name__ == "__main__":
    main()
