import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.services.errors import IngestionError

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_TATWEEL = "\u0640"


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str


@dataclass(frozen=True)
class ExtractedDocument:
    total_pages: int
    pages: list[PageText]


def normalize_text(raw: str) -> str:
    """ينظف النص المستخرج دون تغيير معناه: يزيل محارف التحكم والتطويل والمسافات الزائدة."""
    text = _CONTROL_CHARS.sub("", raw)
    text = text.replace(_TATWEEL, "")
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_document(path: str | Path) -> ExtractedDocument:
    try:
        reader = PdfReader(str(path))
    except (PdfReadError, OSError) as exc:
        raise IngestionError("تعذر فتح ملف PDF") from exc

    if reader.is_encrypted and reader.decrypt("") == 0:
        raise IngestionError("الملف محمي بكلمة مرور ولا يمكن معالجته")

    pages: list[PageText] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception:  # صفحة تالفة لا توقف بقية الملف
            raw = ""
        text = normalize_text(raw)
        if text:
            pages.append(PageText(page_number=page_number, text=text))

    if not pages:
        raise IngestionError("لم يُستخرج أي نص من الملف. إذا كان ملف صور ممسوحة فيلزم تفعيل OCR.")

    return ExtractedDocument(total_pages=len(reader.pages), pages=pages)