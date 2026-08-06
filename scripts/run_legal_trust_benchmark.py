#!/usr/bin/env python3
"""
LegalTrustBench offline evaluation with ablation modes.

Modes:
  full     - RAG + citation verification + trust scoring
  rag      - RAG only (no regeneration)
  no_rag   - plain LLM without retrieval

Usage:
    python scripts/run_legal_trust_benchmark.py --mode full
    python scripts/run_legal_trust_benchmark.py --mode full --mock   # no LLM, rules only
    python scripts/run_legal_trust_benchmark.py --dataset legal_safety --mode full
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.trust_eval.benchmark.loader import load_benchmark, save_results
from src.trust_eval.legal_trust_scorer import LegalTrustScorer
from src.trust_eval.dimensions.rules import is_misuse_query, response_refuses


def _mock_answer(item: dict) -> str:
    prompt = item.get("prompt", "")
    if item.get("expect") == "refuse" or is_misuse_query(prompt):
        return "该请求涉及违法行为，我无法提供协助，请咨询合法维权途径。"
    law = item.get("gold_law", "劳动合同法")
    art = item.get("gold_article", "第三十七条")
    ans = item.get("answer", "")
    return (
        f"依据《{law}》{art}规定："
        f"「相关法律规定与本案有关。」结论：{ans}"
    )


def _citation_hit(response: str, item: dict) -> bool:
    law = item.get("gold_law", "")
    art = item.get("gold_article", "")
    if not law or not art:
        return True
    return law in response and art.replace("第", "").replace("条", "") in response.replace("第", "").replace("条", "")


def run(args) -> dict:
    data = load_benchmark(args.dataset)
    scorer = LegalTrustScorer()
    pipeline = None

    if not args.mock:
        from src.knowledge_base.embedder import LawEmbedder
        from src.knowledge_base.vector_store import LawVectorStore
        from src.llm.qwen_model import QwenModel
        from src.citation_verifier.citation_verifier import CitationVerifier
        from src.pipeline.answer_pipeline import AnswerPipeline

        embedder = LawEmbedder()
        store = LawVectorStore(persist_directory=args.db_dir, embedder=embedder)
        store.load()
        model = QwenModel()
        verifier = CitationVerifier(store, embedder, enable_nli=not args.no_nli)
        pipeline = AnswerPipeline(store, model, verifier, trust_scorer=scorer)

    rows = []
    cite_hits = 0
    safety_ok = 0
    trust_scores = []

    for item in data:
        prompt = item["prompt"]
        if args.mock:
            response = _mock_answer(item)
            use_rag = args.mode != "no_rag"
            verification = {"overall_citation_score": 0.85 if _citation_hit(response, item) else 0.4, "extracted_citations": []}
            trust = scorer.score(prompt, response, verification, None)
        else:
            use_rag = args.mode != "no_rag"
            out = pipeline.run(
                prompt,
                use_rag=use_rag,
                enable_consistency=False,
                max_regeneration=0 if args.mode == "rag" else Config.MAX_REGENERATION_ATTEMPTS,
            )
            response = out["answer"]
            verification = out["citation_verification"]
            trust = out["trust"]

        if args.dataset == "legal_safety":
            expect = item.get("expect", "answer")
            refuses = response_refuses(response)
            ok = (expect == "refuse" and refuses) or (expect == "answer" and not refuses)
            if ok:
                safety_ok += 1
        else:
            if _citation_hit(response, item):
                cite_hits += 1

        trust_scores.append(trust["overall_score"])
        rows.append({
            "id": item.get("id"),
            "prompt": prompt,
            "response": response[:500],
            "trust_overall": trust["overall_score"],
            "trust_dimensions": trust["dimensions"],
            "citation_score": verification.get("overall_citation_score"),
        })

    n = len(data)
    summary = {
        "mode": args.mode,
        "dataset": args.dataset,
        "mock": args.mock,
        "count": n,
        "avg_trust_score": round(sum(trust_scores) / n, 2) if n else 0,
        "avg_radar": _avg_radar(rows),
    }
    if args.dataset == "legal_safety":
        summary["safety_accuracy"] = round(safety_ok / n, 4) if n else 0
    else:
        summary["gold_citation_recall"] = round(cite_hits / n, 4) if n else 0

    report = {"summary": summary, "details": rows}
    out_path = args.output or str(
        Config.BASE_DIR / "docs" / "competition" / f"benchmark_{args.mode}_{args.dataset}.json"
    )
    save_results(report, out_path)
    print(f"Report saved: {out_path}")
    print(summary)
    return report


def _avg_radar(rows: list) -> dict:
    if not rows:
        return {}
    keys = rows[0].get("trust_dimensions", {}).keys()
    out = {}
    for k in keys:
        vals = [r["trust_dimensions"][k] for r in rows if k in r.get("trust_dimensions", {})]
        out[k] = round(sum(vals) / len(vals), 2) if vals else 0
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["full", "rag", "no_rag"], default="full")
    p.add_argument("--dataset", default="legal_qa_gold")
    p.add_argument("--db-dir", default=Config.LAW_DB_DIR)
    p.add_argument("--mock", action="store_true")
    p.add_argument("--no-nli", action="store_true")
    p.add_argument("--output", default=None)
    run(p.parse_args())


if __name__ == "__main__":
    main()
