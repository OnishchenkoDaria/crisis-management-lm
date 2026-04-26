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

    # present objects as string data
    def __str__(self):
        return (f"{self.__class__.__name__}(id={self.id}, "
                f"external_id={self.external_id!r},"
                f"question={self.question!r})"
                f"answer={self.answer!r})")

    def __repr__(self):
        return str(self)

    # transform received data into dictionary
    def to_dict(self):
        return {
            "id": self.id,
            "external_id": self.external_id,
            "question": self.question,
            "answer": self.answer,
        }