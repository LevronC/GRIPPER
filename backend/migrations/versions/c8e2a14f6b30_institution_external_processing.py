"""institution external-processing authorization

Adds institutions.external_processing_authorized (default false). The runtime role
already has SELECT on the table and does not have UPDATE, so only an owner-connection
script can change the flag. Deployment flags still have to allow external calls.

Revision ID: c8e2a14f6b30
Revises: 4f1b6c8d2e59
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8e2a14f6b30"
down_revision: Union[str, Sequence[str], None] = "4f1b6c8d2e59"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "institutions",
        sa.Column(
            "external_processing_authorized",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("institutions", "external_processing_authorized")
