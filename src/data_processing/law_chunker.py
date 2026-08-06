"""Convert LawArticle objects into LangChain Documents for vector indexing."""
from typing import List
from langchain_core.documents import Document
from .law_parser import LawArticle


class LawChunker:
    """One article → one Document.  Metadata is stored verbatim for exact-match retrieval."""

    def chunk(self, articles: List[LawArticle]) -> List[Document]:
        return [self._to_document(a) for a in articles]

    def _hierarchy_path(self, a: LawArticle) -> List[str]:
        return [p for p in (a.part, a.sub_part, a.chapter, a.section) if p]

    def _hierarchy_label(self, a: LawArticle) -> str:
        return " / ".join(self._hierarchy_path(a))

    def _to_document(self, a: LawArticle) -> Document:
        header = f"【{a.law_name}】{a.article_num}"
        body = f"{header}\n{a.content}"
        hierarchy = self._hierarchy_label(a)
        if hierarchy:
            body = f"{header}（{hierarchy}）\n{a.content}"

        path = self._hierarchy_path(a)
        return Document(
            page_content=body,
            metadata={
                "law_name": a.law_name,
                "article_num": a.article_num,
                "article_num_int": a.article_num_int,
                "effective_date": a.effective_date,
                "category": a.category,
                "part": a.part,
                "sub_part": a.sub_part,
                "chapter": a.chapter,
                "section": a.section,
                "hierarchy_path": " / ".join(path),
                "source": f"{a.law_name}{a.article_num}",
                "status": a.status or "effective",
                "repeal_date": a.repeal_date or "",
                "superseded_by": a.superseded_by or "",
                "law_version": a.law_version or "",
            },
        )
