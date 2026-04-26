from app.database import Base, str_uniq, int_pk, str_not_null, str_null_true
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from typing import Any

class Tactic(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), index=True, nullable=False)
    description: Mapped[str_not_null]
    when_to_apply: Mapped[str_null_true]
    example: Mapped[str_null_true]
    anti_pattern: Mapped[str_null_true]
    crisis_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    source_slug: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    source_chunk_id: Mapped[str] = mapped_column(String(240), index=True, nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # present objects as string data
    def __str__(self):
        return (f"{self.__class__.__name__}(id={self.id}, "
                f"slug={self.slug!r},"
                f"description={self.description!r})")

    def __repr__(self):
        return str(self)

    # transform received data into dictionary
    def to_dict(self):
        return {
            "id": self.id,
            "slug": self.slug,
            "description": self.description,
        }