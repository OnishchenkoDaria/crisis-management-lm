from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Text, JSON, ForeignKey, Integer, String
from app.database import Base, int_pk, str_not_null, str_uniq


try:
    from pgvector.sqlalchemy import Vector
    _PGVECTOR = True
except ImportError:
    _PGVECTOR = False

class RagChunk(Base):
    id: Mapped[int_pk]
    chunk_id: Mapped[str_uniq]  # e.g. "cerc-introduction__ch000__ck001"

    # source document link
    source_document_id: Mapped[int] = mapped_column(
        ForeignKey("sourcedocuments.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    source_document: Mapped["SourceDocument"] = relationship(back_populates="rag_chunks")

    # chunk content
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_title: Mapped[str_not_null]
    source_chapter: Mapped[str_not_null]  # chapter_title from manifest

    # chunk position metadata (from chunk_manifest.json)
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    language: Mapped[str] = mapped_column(String(20), nullable=False, default="mixed")

    # classification tags (populated post-extraction)
    topics: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    scenario_relevance: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # pgvector — 1536 dims (OpenAI text-embedding-3-small)
    # Falls back to JSONB if pgvector not installed yet
    if _PGVECTOR:
        embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    else:
        embedding: Mapped[list[float] | None] = mapped_column(JSONB, nullable=True)

    # present objects as string data
    def __str__(self):
        return (f"{self.__class__.__name__}(id={self.id}, "
                f"chunk_id={self.chunk_id!r},"
                f"source_title={self.source_title!r})"
                f"source_chapter={self.source_chapter!r})")

    def __repr__(self):
        return str(self)

    # transform received data into dictionary
    def to_dict(self):
        return {
            "id": self.id,
            "chunk_id": self.chunk_id,
            "source_title": self.source_title,
            "source_chapter": self.source_chapter,
            "token_count": self.token_count,
            "page_start": self.page_start,
            "page_end": self.page_end,
        }