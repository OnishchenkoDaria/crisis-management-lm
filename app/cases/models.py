from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base, int_pk, str_not_null, str_null_true
from typing import Any, Dict, Optional

# cases
# id
# workspace_id
# title (опц)
# description (text)
# source_text (text) (користувач вставляє текст посту/новини вручну — без storage)
# questionnaire_json (jsonb) (агресія, масштаб, тривалість…)
# status (draft/analyzed)

class Case(Base):
    id: Mapped[int_pk]
    workspace_id: Mapped[int] = mapped_column(ForeignKey('workspaces.id'))

    title: Mapped[str_null_true]
    description: Mapped[str_not_null]
    source_text: Mapped[str] = mapped_column(Text, nullable=False) # user pastes source sample text

    constraints: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    status: Mapped[str] = mapped_column(
        Enum('draft', 'pending', 'analysed', name='status_enum', create_type=False),
        nullable=False
    )

    # present objects as string data
    def __str__(self):
        return (f"{self.__class__.__name__}(id={self.id}, "
                f"case={self.title!r},"
                f"status={self.status!r})")

    def __repr__(self):
        return str(self)