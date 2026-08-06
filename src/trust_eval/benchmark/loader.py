"""Load and save LegalTrustBench datasets."""
import json
from pathlib import Path
from typing import Any, Dict, List

from src.config import Config

BENCHMARK_DIR = Config.BASE_DIR / "data" / "benchmark"


def load_benchmark(name: str = "legal_qa_gold") -> List[Dict[str, Any]]:
    path = BENCHMARK_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def save_results(results: Dict[str, Any], path: str) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
