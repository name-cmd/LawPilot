"""Minimal KB (~30 articles) for CI / low-memory environments."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.data_processing.law_chunker import LawChunker
from src.data_processing.law_parser import LawParser
from src.knowledge_base.embedder import LawEmbedder
from src.knowledge_base.vector_store import LawVectorStore

MINIMAL = {"劳动合同法", "刑法", "劳动法"}


def main() -> None:
    parser = LawParser()
    articles = []
    for jf in Path(Config.PROCESSED_DATA_DIR).glob("*.json"):
        if jf.stem not in MINIMAL:
            continue
        articles.extend(parser.parse_json(str(jf)))
    documents = LawChunker().chunk(articles)
    print(f"Minimal KB: {len(articles)} articles")
    store = LawVectorStore(
        persist_directory=Config.LAW_DB_DIR,
        embedder=LawEmbedder(device="cpu"),
    )
    store.build(documents, batch_size=10)


if __name__ == "__main__":
    main()
