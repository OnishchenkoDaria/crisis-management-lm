from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, JSON
from app.database import Base, int_pk, str_not_null, str_uniq


class QAPair(Base):
    id: Mapped[int_pk]
    external_id: Mapped[str_uniq]  # "qa-0041"
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    scenario_tags: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    difficulty: Mapped[str_not_null]
    common_mistake: Mapped[str] = mapped_column(Text, nullable=False)
    source_scenario_id: Mapped[str_not_null]