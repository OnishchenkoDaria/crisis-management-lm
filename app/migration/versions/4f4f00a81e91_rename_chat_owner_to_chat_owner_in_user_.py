"""rename chat-owner to chat_owner in user_role_enum

Revision ID: 4f4f00a81e91
Revises: 070a8bc2d632
Create Date: 2026-05-18 14:15:16.664992

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f4f00a81e91'
down_revision: Union[str, Sequence[str], None] = '070a8bc2d632'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE user_role_enum RENAME VALUE 'chat-owner' TO 'chat_owner'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TYPE user_role_enum RENAME VALUE 'chat_owner' TO 'chat-owner'"
    )