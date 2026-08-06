"""Law validity / timeliness checks against registry and document metadata."""
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from langchain_core.documents import Document

from src.config import Config
from src.knowledge_base.law_name_resolver import law_name_candidates, resolve_law_name


@dataclass
class ValidityResult:
    effective: bool
    status: str = "effective"
    repeal_date: str = ""
    superseded_by: str = ""
    warning_message: str = ""

    def to_dict(self) -> Dict:
        return {
            "effective": self.effective,
            "status": self.status,
            "repeal_date": self.repeal_date,
            "superseded_by": self.superseded_by,
            "warning_message": self.warning_message,
        }


class LawValidityService:
    """Check whether laws/articles are currently effective."""

    def __init__(self, registry_path: str = None):
        self.registry_path = registry_path or str(
            Config.BASE_DIR / "data" / "law_registry.json"
        )
        self._registry: Optional[Dict] = None

    @property
    def registry(self) -> Dict:
        if self._registry is None:
            self._registry = self._load_registry()
        return self._registry

    def _load_registry(self) -> Dict:
        p = Path(self.registry_path)
        if not p.exists():
            return {}
        import json

        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def reload(self) -> None:
        self._registry = None

    def _lookup_registry(self, law_name: str) -> Optional[Dict]:
        for candidate in law_name_candidates(law_name):
            if candidate in self.registry:
                return self.registry[candidate]
            # Also try without 《》
            bare = candidate.strip("《》")
            if bare in self.registry:
                return self.registry[bare]
        return None

    def is_effective(
        self,
        law_name: str,
        article_num: Optional[str] = None,
        as_of_date: Optional[str] = None,
        doc_metadata: Optional[Dict] = None,
    ) -> ValidityResult:
        """Check law/article validity from registry and optional doc metadata."""
        _ = article_num  # article-level repeal reserved for future use
        _ = as_of_date

        if doc_metadata:
            status = doc_metadata.get("status") or "effective"
            if status in ("repealed", "superseded"):
                superseded = doc_metadata.get("superseded_by") or ""
                repeal = doc_metadata.get("repeal_date") or ""
                msg = f"《{law_name}》已废止"
                if repeal:
                    msg += f"（{repeal}）"
                if superseded:
                    msg += f"，请参见《{superseded}》"
                return ValidityResult(
                    effective=False,
                    status=status,
                    repeal_date=repeal,
                    superseded_by=superseded,
                    warning_message=msg,
                )

        reg = self._lookup_registry(law_name)
        if reg and reg.get("status") in ("repealed", "superseded"):
            superseded = reg.get("superseded_by") or ""
            repeal = reg.get("repeal_date") or ""
            canonical = resolve_law_name(law_name)
            msg = f"《{canonical}》已废止"
            if repeal:
                msg += f"（{repeal}）"
            if superseded:
                msg += f"，请参见《{superseded}》"
            return ValidityResult(
                effective=False,
                status=reg.get("status", "repealed"),
                repeal_date=repeal,
                superseded_by=superseded,
                warning_message=msg,
            )

        return ValidityResult(effective=True, status="effective")

    def check_citation(
        self,
        law_name: str,
        article_num: str,
        doc_metadata: Optional[Dict] = None,
    ) -> ValidityResult:
        return self.is_effective(
            law_name=law_name,
            article_num=article_num,
            doc_metadata=doc_metadata,
        )

    def filter_documents(
        self,
        docs: List[Document],
        as_of_date: Optional[str] = None,
    ) -> List[Document]:
        """Keep only currently effective articles."""
        _ = as_of_date
        filtered: List[Document] = []
        for doc in docs:
            m = doc.metadata or {}
            law = m.get("law_name", "")
            status = m.get("status") or "effective"
            if status in ("repealed", "superseded"):
                continue
            reg = self._lookup_registry(law)
            if reg and reg.get("status") in ("repealed", "superseded"):
                continue
            filtered.append(doc)
        return filtered

    def collect_warnings_from_citations(
        self, citation_results: List[Dict]
    ) -> List[str]:
        warnings: List[str] = []
        seen: set = set()
        for c in citation_results:
            validity = c.get("validity") or {}
            msg = validity.get("warning_message") or ""
            if msg and msg not in seen:
                seen.add(msg)
                warnings.append(msg)
        return warnings
