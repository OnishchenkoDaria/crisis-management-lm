from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base, int_pk, str_not_null
from typing import Any, Dict, Optional


class Workspace(Base):
    id: Mapped[int_pk]
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    name: Mapped[str_not_null]
    voice_profile: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,  # python-side default
        server_default="{}"  # db-side default
    )

    constraints: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    channels: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )