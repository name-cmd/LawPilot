"""
Build a lightweight vector store (excludes full 民法典) for demo / low-memory hosts.

Usage:
    python scripts/build_demo_knowledge_base.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.data_processing.law_chunker import LawChunker
from src.data_processing.law_parser import LawParser
from src.knowledge_base.embedder import LawEmbedder
from src.knowledge_base.vector_store import LawVectorStore

DEMO_LAWS = {
    "劳动合同法", "刑法", "劳动法", "宪法", "民事诉讼法",
    "道路交通安全法", "消费者权益保护法", "公司法", "著作权法",
    "环境保护法", "治安管理处罚法",
}


def main() -> None:
    processed = Path(Config.PROCESSED_DATA_DIR)
    parser = LawParser()
    articles = []
    for jf in sorted(processed.glob("*.json")):
        if jf.stem not in DEMO_LAWS:
            continue
        articles.extend(parser.parse_json(str(jf)))

    print(f"Demo KB: {len(DEMO_LAWS)} laws, {len(articles)} articles")
    chunker = LawChunker()
    documents = chunker.chunk(articles)
    embedder = LawEmbedder(device="cpu")
    store = LawVectorStore(persist_directory=Config.LAW_DB_DIR, embedder=embedder)
    store.build(documents, batch_size=50)
    print(f"Saved to {Config.LAW_DB_DIR}")


if __name__ == "__main__":
    main()
