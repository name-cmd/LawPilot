"""BGE embedding model wrapper (local path, no internet required at runtime)."""
from typing import List
import torch
from langchain_community.embeddings import HuggingFaceEmbeddings
from src.config import Config


def _resolve_device(requested: str = None) -> str:
    dev = requested or Config.EMBEDDING_DEVICE
    if dev == "cuda" and not torch.cuda.is_available():
        return "cpu"
    return dev


class LawEmbedder:
    def __init__(self, model_path: str = None, device: str = None):
        model_path = model_path or Config.EMBEDDING_MODEL_PATH
        device = _resolve_device(device)
        self._embeddings = HuggingFaceEmbeddings(
            model_name=model_path,
            model_kwargs={"device": device},
            encode_kwargs={
                "normalize_embeddings": True,
                "batch_size": Config.EMBEDDING_BATCH_SIZE,
            },
        )

    def embed_query(self, text: str) -> List[float]:
        return self._embeddings.embed_query(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embeddings.embed_documents(texts)

    def get_langchain_embeddings(self) -> HuggingFaceEmbeddings:
        return self._embeddings
