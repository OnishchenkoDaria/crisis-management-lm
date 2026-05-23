"""analysis table renamed

Revision ID: b39ec5764926
Revises: 735aee6b0ab6
Create Date: 2026-05-23 23:59:50.573542

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b39ec5764926'
down_revision: Union[str, Sequence[str], None] = '735aee6b0ab6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Rename the double-s table
    op.rename_table("analysiss", "analyses")

    # Change id column from integer to varchar(36)
    op.alter_column(
        "analyses", "id",
        existing_type=sa.Integer(),
        type_=sa.String(36),
        postgresql_using="id::varchar",
    )

def downgrade() -> None:
    op.alter_column(
        "analyses", "id",
        existing_type=sa.String(36),
        type_=sa.Integer(),
        postgresql_using="id::integer",
    )
    op.rename_table("analyses", "analysiss")
    # ### end Alembic commands ###
