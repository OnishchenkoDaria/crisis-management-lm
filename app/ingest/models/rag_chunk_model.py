from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, JSON
from app.database import Base, int_pk, str_not_null, str_uniq


class RagChunk(Base):
    id: Mapped[int_pk]
    chunk_id: Mapped[str_uniq]  # "ch-0892"
    text: Mapped[str] = mapped_column(Text, nullable=False)
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