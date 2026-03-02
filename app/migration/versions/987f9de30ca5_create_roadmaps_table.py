"""create roadmaps table

Revision ID: 987f9de30ca5
Revises: 4ef57809789e
Create Date: 2026-03-02 20:58:09.812536
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '987f9de30ca5'
down_revision: Union[str, Sequence[str], None] = '4ef57809789e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# enums (idempotent)
phase_enum = postgresql.ENUM(
    'T0_30M', 'T30M_2H', 'H2_24H', 'D1_7', 'MONITORING',
    name='phase_enum',
    create_type=False,
)

item_type_enum = postgresql.ENUM(
    'STRATEGY', 'TACTIC', 'MESSAGE', 'MONITORING',
    name='item_type_enum',
    create_type=False,
)

priority_enum = postgresql.ENUM(
    'P0', 'P1', 'P2',
    name='priority_enum',
    create_type=False,
)

status_enum = postgresql.ENUM(
    'TODO', 'DOING', 'DONE', 'BLOCKED',
    name='status_enum',
    create_type=False,
)

def upgrade() -> None:
    bind = op.get_bind()

    # create types if missing (won’t collide if they already exist)
    phase_enum.create(bind, checkfirst=True)
    item_type_enum.create(bind, checkfirst=True)
    priority_enum.create(bind, checkfirst=True)
    status_enum.create(bind, checkfirst=True)

    op.create_table(
        'roadmaps',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('cases.id'), nullable=False),

        sa.Column('phase', phase_enum, nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),

        sa.Column('item_type', item_type_enum, nullable=False),
        sa.Column('priority', priority_enum, nullable=False),
        sa.Column('status', status_enum, nullable=False),

        sa.Column('due_at', sa.DateTime(), nullable=True),
        sa.Column('ai_rationale', sa.String(), nullable=True),
        sa.Column('risk_if_skipped', sa.String(), nullable=True),
        sa.Column('order_index', sa.Integer(), nullable=False),

        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    )

def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table('roadmaps')

    # only drop these if nothing else uses them
    status_enum.drop(bind, checkfirst=True)
    priority_enum.drop(bind, checkfirst=True)
    item_type_enum.drop(bind, checkfirst=True)
    phase_enum.drop(bind, checkfirst=True)