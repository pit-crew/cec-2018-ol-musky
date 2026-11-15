"""Baseline schema.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_parameter",
        sa.Column("scenario_id", sa.String(32), primary_key=True),
        sa.Column("lifetime", sa.Integer, nullable=False),
        sa.Column("rows", sa.Integer, nullable=False),
        sa.Column("cols", sa.Integer, nullable=False),
        sa.Column("hub_capacity", sa.Integer, nullable=False),
        sa.Column("mining_rate", sa.Integer, nullable=False),
        sa.Column("starting_capital", sa.Integer, nullable=False),
        sa.Column("ms_per_week", sa.Integer, nullable=False),
        sa.Column("prospecting_offset", sa.Integer, nullable=False),
    )
    op.create_table(
        "mcp_cost",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "parameter_id",
            sa.String(32),
            sa.ForeignKey("mcp_parameter.scenario_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item", sa.String(16), nullable=False),
        sa.Column("weeks", sa.Integer, nullable=False),
        sa.Column("rate", sa.Float, nullable=False),
    )
    op.create_index("ix_mcp_cost_parameter_id", "mcp_cost", ["parameter_id"])
    op.create_table(
        "mcp_belt",
        sa.Column("sector_id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("ore_id", sa.String(8), nullable=False),
        sa.Column("deposit_amt", sa.Integer, nullable=False),
    )
    op.create_table(
        "mcp_team",
        sa.Column("token", sa.String(40), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("week", sa.Integer, nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("balance", sa.Integer, nullable=False),
    )

    def team_fk() -> sa.Column:
        return sa.Column(
            "team_id",
            sa.String(40),
            sa.ForeignKey("mcp_team.token", ondelete="CASCADE"),
            nullable=False,
        )

    op.create_table(
        "mcp_ledger",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        team_fk(),
        sa.Column("week", sa.Integer, nullable=False),
        sa.Column("item", sa.String(32), nullable=False),
        sa.Column("credit", sa.Float, nullable=False),
        sa.Column("debit", sa.Float, nullable=False),
    )
    op.create_index("ix_mcp_ledger_team_id", "mcp_ledger", ["team_id"])
    op.create_table(
        "mcp_hub",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        team_fk(),
        sa.Column("hub_id", sa.String(8), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sector_id", sa.Integer, nullable=False),
        sa.Column("amt", sa.JSON, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("space_remaining", sa.Integer, nullable=False),
        sa.UniqueConstraint("team_id", "hub_id", name="uq_mcp_hub_team_hub"),
    )
    op.create_table(
        "mcp_site",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        team_fk(),
        sa.Column("sector_id", sa.Integer, nullable=False),
        sa.Column("ore_id", sa.String(8), nullable=False),
        sa.Column("deposit_amt", sa.Integer, nullable=False),
        sa.UniqueConstraint("team_id", "sector_id", name="uq_mcp_site_team_sector"),
    )
    op.create_table(
        "mcp_order",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        team_fk(),
        sa.Column("week", sa.Integer, nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("hub_list", sa.Text, nullable=False),
        sa.Column("sector_id_list", sa.Text, nullable=False),
        sa.Column("ore_load", sa.JSON, nullable=False),
        sa.Column("complete", sa.Boolean, nullable=False),
        sa.Column("insured", sa.Boolean, nullable=False),
        sa.Column("pirated", sa.Boolean, nullable=False),
    )
    op.create_index("ix_mcp_order_team_complete", "mcp_order", ["team_id", "complete"])


def downgrade() -> None:
    for table in (
        "mcp_order",
        "mcp_site",
        "mcp_hub",
        "mcp_ledger",
        "mcp_team",
        "mcp_belt",
        "mcp_cost",
        "mcp_parameter",
    ):
        op.drop_table(table)
