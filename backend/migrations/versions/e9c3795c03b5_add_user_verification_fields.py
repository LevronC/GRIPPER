"""add_user_verification_fields

Revision ID: e9c3795c03b5
Revises: b147efed605a
Create Date: 2026-05-26 07:25:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e9c3795c03b5'
down_revision = 'b147efed605a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add column as nullable first
    op.add_column('users', sa.Column('is_verified', sa.Boolean(), nullable=True))
    op.add_column('users', sa.Column('verification_code', sa.String(length=6), nullable=True))
    
    # 2. Update existing rows
    op.execute("UPDATE users SET is_verified = FALSE")
    
    # 3. Make non-nullable
    op.alter_column('users', 'is_verified', nullable=False)


def downgrade() -> None:
    op.drop_column('users', 'verification_code')
    op.drop_column('users', 'is_verified')
