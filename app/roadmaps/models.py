from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey, Enum, DateTime, Integer
from app.database import Base, int_pk, str_not_null, str_null_true
from app.roadmaps.schema import PhaseEnum, ItemTypeEnum, PriorityEnum, StatusEnum, CreatedByEnum

# id
# case_id
# phase (enum: T0_30M, T30M_2H, H2_24H, D1_7, MONITORING)
# title
# description
# item_type (strategy/tactic/message/monitoring)
# priority (P0/P1/P2)
# status (todo/doing/done/blocked)
# due_at (nullable)
# ai_rationale (text)
# risk_if_skipped (text)
# order_index (int)
# created_by (ai/user)

class Roadmap(Base):
    id: Mapped[int_pk]
    case_id: Mapped[int] = mapped_column(ForeignKey('cases.id'))

    phase: Mapped[PhaseEnum] = mapped_column(
        Enum(PhaseEnum, name="phase_enum"),
        nullable=False
    )
    title: Mapped[str_not_null]
    description: Mapped[str_null_true]

    item_type: Mapped[ItemTypeEnum] = mapped_column(
        Enum(ItemTypeEnum, name="item_type_enum"),
        nullable=False
    )

    priority: Mapped[PriorityEnum] = mapped_column(
        Enum(PriorityEnum, name="priority_enum"),
        nullable=False,
        default=PriorityEnum.P1
    )

    status: Mapped[StatusEnum] = mapped_column(
        Enum(StatusEnum, name="status_enum"),
        nullable=False,
        default=StatusEnum.TODO
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    ai_rationale: Mapped[str_null_true]
    risk_if_skipped: Mapped[str_null_true]

    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # present objects as string data
    def __str__(self):
        return (
            f"<RoadmapItem(id={self.id}, "
            f"phase={self.phase}, "
            f"priority={self.priority}, "
            f"status={self.status})>"
        )

    def __repr__(self):
        return str(self)