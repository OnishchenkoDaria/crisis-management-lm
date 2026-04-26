from app.database import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from typing import Any


class SourceDocument(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_slug: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    language: Mapped[str] = mapped_column(String(20), nullable=False, default="mixed")
    doc_type: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    rag_chunks: Mapped[list["RagChunk"]] = relationship(back_populates="source_document", cascade="all, delete-orphan")

    # present objects as string data
    def __str__(self):
        return (f"{self.__class__.__name__}(id={self.id}, "
                f"source_slug={self.source_slug!r},"
                f"file_name={self.file_name!r})")

    def __repr__(self):
        return str(self)

    # transform received data into dictionary
    def to_dict(self):
        return {
            "id": self.id,
            "source_slug": self.source_slug,
            "file_name": self.file_name,
        }