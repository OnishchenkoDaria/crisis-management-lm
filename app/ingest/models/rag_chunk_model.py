from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, JSON, ForeignKey
from app.database import Base, int_pk, str_not_null, str_uniq


class RagChunk(Base):
    id: Mapped[int_pk]
    chunk_id: Mapped[str_uniq]  # "ch-0892"
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_document_id: Mapped[int] = mapped_column(
        ForeignKey("sourcedocuments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_title: Mapped[str_not_null]
    source_chapter: Mapped[str_not_null]
    topics: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    scenario_relevance: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        JSON, nullable=True
    )

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
        }