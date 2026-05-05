from app.database import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB


class TrainingSample(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_qa_id: Mapped[int | None] = mapped_column(ForeignKey("qapairs.id"), nullable=True)
    messages: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False)
    format: Mapped[str] = mapped_column(String(40), nullable=False, default="messages")

    # present objects as string data
    def __str__(self):
        return (f"{self.__class__.__name__}(id={self.id}, "
                f"source_qa_id={self.source_qa_id!r},"
                f"messages={self.messages!r})")

    def __repr__(self):
        return str(self)

    # transform received data into dictionary
    def to_dict(self):
        return {
            "id": self.id,
            "source_qa_id": self.source_qa_id,
            "messages": self.messages,
        }