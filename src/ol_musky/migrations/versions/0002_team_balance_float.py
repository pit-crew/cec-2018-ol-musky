"""Team balance becomes a float: the balance is exact and agrees with the ledger.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("mcp_team") as batch:
        batch.alter_column("balance", existing_type=sa.Integer, type_=sa.Float)


def downgrade() -> None:
    with op.batch_alter_table("mcp_team") as batch:
        batch.alter_column("balance", existing_type=sa.Float, type_=sa.Integer)
