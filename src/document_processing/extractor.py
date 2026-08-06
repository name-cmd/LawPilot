"""
Multi-format document text extractor.

Strategy (per document type):
- txt/md: direct read with encoding detection
- docx: python-docx (paragraphs + tables)
- pdf: PyMuPDF text layer; OCR fallback for scanned pages
- images: PaddleOCR
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from src.config import Config

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}
_TEXT_EXTS = {".txt", ".md", ".markdown", ".csv", ".log"}
_DOCX_EXTS = {".docx"}
_PDF_EXTS = {".pdf"}
_SUPPORTED_EXTS = _IMAGE_EXTS | _TEXT_EXTS | _DOCX_EXTS | _PDF_EXTS

_MIN_PAGE_TEXT_CHARS = 30


@dataclass
class PageExtraction:
    page_num: int
    text: str
    method: str  # "text" | "ocr"


@dataclass
class ExtractionResult:
    filename: str
    text: str
    format: str
    char_count: int
    page_count: int = 0
    extraction_methods: List[str] = field(default_factory=list)
    pages: List[PageExtraction] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "text": self.text,
            "format": self.format,
            "char_count": self.char_count,
            "page_count": self.page_count,
            "extraction_methods": self.extraction_methods,
            "warnings": self.warnings,
        }


class DocumentExtractor:
    """Extract plain text from supported file formats."""

    def __init__(self, ocr_enabled: bool = True):
        self.ocr_enabled = ocr_enabled
        self._ocr_engine = None

    @staticmethod
    def supported_extensions() -> List[str]:
        return sorted(_SUPPORTED_EXTS)

    @staticmethod
    def is_supported(filename: str) -> bool:
        return Path(filename).suffix.lower() in _SUPPORTED_EXTS

    def extract_bytes(self, data: bytes, filename: str) -> ExtractionResult:
        ext = Path(filename).suffix.lower()
        if ext not in _SUPPORTED_EXTS:
            raise ValueError(
                f"不支持的文件格式「{ext}」，"
                f"支持：{', '.join(sorted(_SUPPORTED_EXTS))}"
            )
        if len(data) > Config.DOC_MAX_UPLOAD_BYTES:
            raise ValueError(
                f"文件过大（{len(data) // 1024} KB），"
                f"上限 {Config.DOC_MAX_UPLOAD_BYTES // 1024 // 1024} MB"
            )

        if ext in _TEXT_EXTS:
            return self._extract_text(data, filename, ext)
        if ext in _DOCX_EXTS:
            return self._extract_docx(data, filename)
        if ext in _PDF_EXTS:
            return self._extract_pdf(data, filename)
        if ext in _IMAGE_EXTS:
            return self._extract_image(data, filename, ext)
        raise ValueError(f"未处理的格式：{ext}")

    def extract_file(self, path: str | Path) -> ExtractionResult:
        path = Path(path)
        data = path.read_bytes()
        return self.extract_bytes(data, path.name)

    # ------------------------------------------------------------------
    # Format handlers
    # ------------------------------------------------------------------

    def _extract_text(self, data: bytes, filename: str, ext: str) -> ExtractionResult:
        text = _decode_text(data)
        text = _normalize_text(text)
        return ExtractionResult(
            filename=filename,
            text=text,
            format=ext.lstrip("."),
            char_count=len(text),
            page_count=1,
            extraction_methods=["text"],
        )

    def _extract_docx(self, data: bytes, filename: str) -> ExtractionResult:
        try:
            from docx import Document
        except ImportError as e:
            raise RuntimeError("缺少 python-docx，请执行 pip install python-docx") from e

        doc = Document(io.BytesIO(data))
        parts: List[str] = []

        for para in doc.paragraphs:
            line = para.text.strip()
            if line:
                parts.append(line)

        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))

        text = _normalize_text("\n".join(parts))
        warnings: List[str] = []
        if not text:
            warnings.append("Word 文档未提取到可见文字，可能为扫描件，请转为 PDF 或图片上传")

        return ExtractionResult(
            filename=filename,
            text=text,
            format="docx",
            char_count=len(text),
            page_count=1,
            extraction_methods=["docx"],
            warnings=warnings,
        )

    def _extract_pdf(self, data: bytes, filename: str) -> ExtractionResult:
        try:
            import fitz  # PyMuPDF
        except ImportError as e:
            raise RuntimeError("缺少 PyMuPDF，请执行 pip install pymupdf") from e

        doc = fitz.open(stream=data, filetype="pdf")
        pages: List[PageExtraction] = []
        methods: set[str] = set()
        warnings: List[str] = []

        for i, page in enumerate(doc):
            page_num = i + 1
            text = _normalize_text(page.get_text("text", sort=True))
            if len(text) >= _MIN_PAGE_TEXT_CHARS:
                pages.append(PageExtraction(page_num, text, "text"))
                methods.add("pdf_text")
                continue

            if self.ocr_enabled:
                ocr_text = self._ocr_page_image(page)
                if ocr_text:
                    pages.append(PageExtraction(page_num, ocr_text, "ocr"))
                    methods.add("ocr")
                    continue

            if text:
                pages.append(PageExtraction(page_num, text, "text"))
                methods.add("pdf_text")
            else:
                warnings.append(f"第 {page_num} 页未能提取文字")

        doc.close()
        full_text = _normalize_text("\n\n".join(p.text for p in pages if p.text))
        if not full_text:
            warnings.append("PDF 未提取到文字，可能为加密或纯扫描件")

        return ExtractionResult(
            filename=filename,
            text=full_text,
            format="pdf",
            char_count=len(full_text),
            page_count=len(pages) or 1,
            extraction_methods=sorted(methods) or ["pdf_text"],
            pages=pages,
            warnings=warnings,
        )

    def _extract_image(self, data: bytes, filename: str, ext: str) -> ExtractionResult:
        text = self._ocr_image_bytes(data)
        warnings: List[str] = []
        if not text:
            warnings.append("图片 OCR 未识别到文字")
        return ExtractionResult(
            filename=filename,
            text=text,
            format=ext.lstrip("."),
            char_count=len(text),
            page_count=1,
            extraction_methods=["ocr"] if text else [],
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # OCR (lazy-loaded: RapidOCR default, PaddleOCR optional)
    # ------------------------------------------------------------------

    def _get_ocr(self):
        if self._ocr_engine is not None:
            return self._ocr_engine
        if not self.ocr_enabled:
            return None

        backend = (Config.OCR_BACKEND or "rapidocr").lower()
        if backend == "paddleocr":
            try:
                from paddleocr import PaddleOCR
            except ImportError as e:
                raise RuntimeError(
                    "缺少 PaddleOCR，请执行 pip install paddleocr paddlepaddle，"
                    "或将 OCR_BACKEND 设为 rapidocr"
                ) from e
            self._ocr_engine = ("paddle", PaddleOCR(lang="ch"))
            return self._ocr_engine

        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as e:
            raise RuntimeError(
                "缺少 OCR 引擎，请执行 pip install rapidocr-onnxruntime，"
                "或 pip install paddleocr paddlepaddle 并将 OCR_BACKEND 设为 paddleocr"
            ) from e
        self._ocr_engine = ("rapid", RapidOCR())
        return self._ocr_engine

    def _ocr_page_image(self, page) -> str:
        try:
            import fitz
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            return self._ocr_image_bytes(pix.tobytes("png"))
        except Exception:
            return ""

    def _ocr_image_bytes(self, data: bytes) -> str:
        engine = self._get_ocr()
        if engine is None:
            return ""
        try:
            import numpy as np
            from PIL import Image

            img = Image.open(io.BytesIO(data)).convert("RGB")
            arr = np.array(img)
            backend, ocr = engine
            if backend == "paddle":
                result = ocr.ocr(arr)
                lines: List[str] = []
                for block in result or []:
                    for line in block or []:
                        if line and len(line) >= 2 and line[1]:
                            lines.append(str(line[1][0]))
                return _normalize_text("\n".join(lines))

            result, _ = ocr(arr)
            lines = [str(item[1]) for item in (result or []) if item and len(item) >= 2]
            return _normalize_text("\n".join(lines))
        except Exception:
            return ""


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _decode_text(data: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
