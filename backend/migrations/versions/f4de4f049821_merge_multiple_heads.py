"""merge multiple heads

Revision ID: f4de4f049821
Revises: a3f9b1c2d4e5, e9c3795c03b5
Create Date: 2026-07-20 12:59:17.109363

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4de4f049821'
down_revision: Union[str, Sequence[str], None] = ('a3f9b1c2d4e5', 'e9c3795c03b5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
