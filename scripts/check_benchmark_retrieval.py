#!/usr/bin/env python3
"""
自检测试集的检索命中率（Hit@1/3/5）：
对 data/benchmark 下每个数据集的每题 prompt 跑向量检索，
检查 gold_law + gold_article 是否出现在 top-k 结果中。

用途：扩充/修改测试集后，确认每题的 gold 条文能被检索到，
避免"检索不可能命中"的废题混入测试集。

用法：
    python scripts/check_benchmark_retrieval.py
    python scripts/check_benchmark_retrieval.py --dataset retrieval_gold
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.knowledge_base.embedder import LawEmbedder
from src.knowledge_base.vector_store import LawVectorStore


def _norm(s: str) -> str:
    """条号归一化：第X条 → X"""
    return (s or "").replace("第", "").replace("条", "").strip()


def check_dataset(store, items, name) -> None:
    hits = {1: 0, 3: 0, 5: 0}
    miss = []
    for item in items:
        docs = store.similarity_search(item["prompt"], k=5)
        gold_law = item["gold_law"]
        gold_art = _norm(item["gold_article"])
        rank = next(
            (
                i
                for i, m in enumerate(docs, 1)
                if gold_law.replace("中华人民共和国", "") in (m.metadata.get("law_name") or "")
                and _norm(m.metadata.get("article_num")) == gold_art
            ),
            None,
        )
        for k in (1, 3, 5):
            if rank and rank <= k:
                hits[k] += 1
        if rank is None:
            miss.append(
                (
                    item["id"],
                    item["prompt"][:24],
                    item["gold_law"],
                    item["gold_article"],
                    [(m.metadata.get("law_name"), m.metadata.get("article_num")) for m in docs[:3]],
                )
            )

    n = len(items)
    print(f"===== {name}（{n} 题）=====")
    print(
        f"  Hit@1 = {hits[1]}/{n} ({hits[1]/n:.1%})"
        f"  Hit@3 = {hits[3]}/{n} ({hits[3]/n:.1%})"
        f"  Hit@5 = {hits[5]}/{n} ({hits[5]/n:.1%})"
    )
    for m in miss:
        print("  MISS:", m)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Check benchmark gold retrieval hit rates")
    parser.add_argument(
        "--dataset",
        default="all",
        choices=["all", "legal_qa_gold", "retrieval_gold"],
        help="要检查的数据集（默认 all）",
    )
    args = parser.parse_args()

    embedder = LawEmbedder(device=Config.EMBEDDING_DEVICE)
    store = LawVectorStore(persist_directory=Config.LAW_DB_DIR, embedder=embedder)
    store.load()

    bench_dir = Path(Config.BASE_DIR) / "data" / "benchmark"
    names = (
        ["legal_qa_gold", "retrieval_gold"]
        if args.dataset == "all"
        else [args.dataset]
    )
    for name in names:
        items = json.loads((bench_dir / f"{name}.json").read_text(encoding="utf-8"))
        check_dataset(store, items, name)


if __name__ == "__main__":
    main()
