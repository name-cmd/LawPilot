"""
Build the ChromaDB vector store from raw law files.

Usage:
    python scripts/build_knowledge_base.py
    python scripts/build_knowledge_base.py --data-dir data/raw --device cpu
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import json
import shutil

from src.config import Config
from src.data_processing.law_parser import LawParser, LawArticle
from src.data_processing.law_chunker import LawChunker
from src.data_processing.repeal_extractor import load_manual_registry
from src.knowledge_base.embedder import LawEmbedder
from src.knowledge_base.vector_store import LawVectorStore


def _apply_registry_to_articles(
    articles: list[LawArticle], registry: dict
) -> list[LawArticle]:
    """Mark articles from repealed laws using law_registry.json."""
    updated: list[LawArticle] = []
    for a in articles:
        reg = registry.get(a.law_name)
        if not reg:
            # try stripping 中华人民共和国
            short = a.law_name.replace("中华人民共和国", "").strip()
            reg = registry.get(short)
        if reg and reg.get("status") in ("repealed", "superseded"):
            a = LawArticle(
                law_name=a.law_name,
                article_num=a.article_num,
                article_num_int=a.article_num_int,
                content=a.content,
                effective_date=a.effective_date,
                category=a.category,
                part=a.part,
                sub_part=a.sub_part,
                chapter=a.chapter,
                section=a.section,
                status=reg.get("status", "repealed"),
                repeal_date=reg.get("repeal_date", ""),
                superseded_by=reg.get("superseded_by", ""),
                law_version=reg.get("law_version", ""),
            )
        elif not a.status:
            a = LawArticle(
                law_name=a.law_name,
                article_num=a.article_num,
                article_num_int=a.article_num_int,
                content=a.content,
                effective_date=a.effective_date,
                category=a.category,
                part=a.part,
                sub_part=a.sub_part,
                chapter=a.chapter,
                section=a.section,
                status="effective",
            )
        updated.append(a)
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Chinese Law Vector Store")
    parser.add_argument("--data-dir", default=Config.RAW_DATA_DIR)
    parser.add_argument("--db-dir", default=Config.LAW_DB_DIR)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--device", default=Config.EMBEDDING_DEVICE,
                        choices=["cuda", "cpu"])
    parser.add_argument(
        "--reset", action="store_true",
        help="构建前清空旧向量库目录（避免新旧数据混合，数据变更后务必加此参数）",
    )
    args = parser.parse_args()

    print("=== 中国法律知识库构建 ===\n")

    if args.reset and Path(args.db_dir).exists():
        shutil.rmtree(args.db_dir)
        print(f"  [--reset] 已清空旧向量库: {args.db_dir}\n")

    registry = load_manual_registry(Config.LAW_REGISTRY_PATH)
    repeals_path = Path(Config.LAW_REPEALS_PATH)
    if repeals_path.exists():
        with open(repeals_path, encoding="utf-8") as f:
            auto = json.load(f)
        registry = {**auto, **registry}

    # 1. Parse (prefer processed JSON, fallback to raw)
    law_parser = LawParser()
    articles = []
    processed = Path(Config.PROCESSED_DATA_DIR)
    if processed.exists():
        print(f"[1/3] 解析 processed JSON ({processed}) …")
        for jf in sorted(processed.glob("*.json")):
            if jf.name == "law_repeals.json":
                continue
            articles.extend(law_parser.parse_json(str(jf)))
    if not articles:
        print(f"[1/3] 解析法律文件 ({args.data_dir}) …")
        articles = law_parser.parse_directory(args.data_dir)
    if not articles:
        print("  未找到法律文件。请将数据集放入 data/raw/ 目录后重试。")
        sys.exit(1)
    articles = _apply_registry_to_articles(articles, registry)
    laws = set(a.law_name for a in articles)
    effective_count = sum(1 for a in articles if a.status == "effective")
    print(
        f"  解析完成：{len(laws)} 部法律，{len(articles)} 条法条"
        f"（有效 {effective_count}，废止/替代 {len(articles) - effective_count}）"
    )

    # 2. Chunk
    print("\n[2/3] 生成文档分片 …")
    chunker = LawChunker()
    documents = chunker.chunk(articles)
    print(f"  生成 {len(documents)} 个文档分片")

    # 3. Embed + store
    print(f"\n[3/3] 向量化并写入 ChromaDB ({args.db_dir}) …")
    embedder = LawEmbedder(device=args.device)
    store = LawVectorStore(persist_directory=args.db_dir, embedder=embedder)
    store.build(documents, batch_size=args.batch_size)

    print("\n=== 构建完成 ===")
    print(f"  法律总数   : {len(laws)}")
    print(f"  法条总数   : {len(articles)}")
    print(f"  向量库路径 : {args.db_dir}")


if __name__ == "__main__":
    main()
