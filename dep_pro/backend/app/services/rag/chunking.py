from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.rag.pdf_loader import PageText

# فواصل تراعي الكتابة العربية (، ؛ ؟) إضافة للفواصل اللاتينية
_SEPARATORS = ["\n\n", "\n", ". ", "؟ ", "؛ ", "، ", "! ", " ", ""]


@dataclass(frozen=True)
class Chunk:
    index: int
    page_number: int | None
    content: str
    token_count: int


def chunk_pages(pages: list[PageText], chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    """
    يقسم كل صفحة على حدة لضمان أن كل مقطع ينتمي إلى صفحة واحدة،
    وهذا يتيح الإشارة إلى رقم الصفحة في الإجابات والكويزات.
    """
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap يجب أن يكون أصغر من chunk_size")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=_SEPARATORS,
        length_function=len,
    )

    chunks: list[Chunk] = []
    index = 0
    for page in pages:
        for piece in splitter.split_text(page.text):
            content = piece.strip()
            if not content:
                continue
            chunks.append(
                Chunk(
                    index=index,
                    page_number=page.page_number,
                    content=content,
                    token_count=len(content.split()),
                )
            )
            index += 1
    return chunks