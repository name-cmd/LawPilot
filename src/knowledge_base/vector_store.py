"""ChromaDB vector store: build, persist, load, and query."""
from typing import List, Optional, Tuple
from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma
from .embedder import LawEmbedder
from .law_name_resolver import law_name_candidates
from src.config import Config


class LawVectorStore:
    def __init__(self, persist_directory: str = None, embedder: LawEmbedder = None):
        self.persist_directory = persist_directory or Config.LAW_DB_DIR
        self.embedder = embedder or LawEmbedder()
        self._db: Optional[Chroma] = None

    # ------------------------------------------------------------------
    # Build / load
    # ------------------------------------------------------------------

    def build(self, documents: List[Document], batch_size: int = 500) -> None:
        """Build and persist vector store from document list."""
        print(f"Building vector store with {len(documents)} documents …")
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            if i == 0:
                self._db = Chroma.from_documents(
                    documents=batch,
                    embedding=self.embedder.get_langchain_embeddings(),
                    persist_directory=self.persist_directory,
                    collection_name=Config.COLLECTION_NAME,
                )
            else:
                self._db.add_documents(batch)
            print(f"  {min(i + batch_size, len(documents))}/{len(documents)} indexed")
        self._db.persist()
        print(f"Saved to {self.persist_directory}")

    def load(self) -> None:
        """Load an existing persisted vector store."""
        self._db = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embedder.get_langchain_embeddings(),
            collection_name=Config.COLLECTION_NAME,
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def similarity_search(
        self, query: str, k: int = None, where: Optional[dict] = None
    ) -> List[Document]:
        k = k or Config.TOP_K_RETRIEVAL
        kwargs = {"k": k}
        if where:
            kwargs["filter"] = where
        return self._db.similarity_search(query, **kwargs)

    def similarity_search_with_score(
        self, query: str, k: int = None, where: Optional[dict] = None
    ) -> List[Tuple[Document, float]]:
        k = k or Config.TOP_K_RETRIEVAL
        kwargs = {"k": k}
        if where:
            kwargs["filter"] = where
        return self._db.similarity_search_with_score(query, **kwargs)

    def similarity_search_unique(
        self, query: str, k: int = None, effective_only: bool = True
    ) -> List[Tuple[Document, float]]:
        """Retrieve top-k unique articles (dedupe by law + article number)."""
        from src.knowledge_base.retrieval_utils import deduplicate_with_scores
        from src.knowledge_base.law_validity import LawValidityService

        k = k or Config.TOP_K_RETRIEVAL
        fetch_k = min(max(k * 3, k), 30)
        where = {"status": {"$eq": "effective"}} if effective_only else None
        try:
            raw = self.similarity_search_with_score(query, k=fetch_k, where=where)
        except Exception:
            raw = self.similarity_search_with_score(query, k=fetch_k)
        deduped = deduplicate_with_scores(raw, max_items=k)
        if effective_only:
            validity = LawValidityService()
            filtered = validity.filter_documents([d for d, _ in deduped])
            key_set = {
                (d.metadata.get("law_name"), d.metadata.get("article_num"))
                for d in filtered
            }
            deduped = [(d, s) for d, s in deduped if (
                d.metadata.get("law_name"), d.metadata.get("article_num")
            ) in key_set]
        return deduped[:k]

    def get_article(self, law_name: str, article_num: str) -> Optional[Document]:
        """Exact-match retrieval by law name + article number (with name normalization)."""
        for candidate in law_name_candidates(law_name):
            doc = self._get_article_exact(candidate, article_num)
            if doc is not None:
                return doc
        return None

    def _get_article_exact(self, law_name: str, article_num: str) -> Optional[Document]:
        try:
            results = self._db.get(
                where={
                    "$and": [
                        {"law_name": {"$eq": law_name}},
                        {"article_num": {"$eq": article_num}},
                    ]
                }
            )
        except Exception:
            return None

        if results and results.get("documents"):
            return Document(
                page_content=results["documents"][0],
                metadata=results["metadatas"][0],
            )
        return None

    def article_exists(self, law_name: str, article_num: str) -> bool:
        return self.get_article(law_name, article_num) is not None
