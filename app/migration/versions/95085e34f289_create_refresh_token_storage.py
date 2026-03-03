"""create refresh token storage

Revision ID: 95085e34f289
Revises: 987f9de30ca5
Create Date: 2026-03-03 03:09:06.401801

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '95085e34f289'
down_revision: Union[str, Sequence[str], None] = '987f9de30ca5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
