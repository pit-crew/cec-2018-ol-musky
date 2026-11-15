"""Persistent data model.

Table and column names agree with the Django application (mcp/models.py), thus the
SQL reports in admin/*.sql continue to operate. The Market table is not kept: the
market price is a function of the week and has no stored state.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Parameter(Base):
    __tablename__ = "mcp_parameter"

    scenario_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    lifetime: Mapped[int] = mapped_column(Integer)
    rows: Mapped[int] = mapped_column(Integer)
    cols: Mapped[int] = mapped_column(Integer)
    hub_capacity: Mapped[int] = mapped_column(Integer)
    mining_rate: Mapped[int] = mapped_column(Integer)
    starting_capital: Mapped[int] = mapped_column(Integer)
    ms_per_week: Mapped[int] = mapped_column(Integer)
    prospecting_offset: Mapped[int] = mapped_column(Integer, default=7)

    costs: Mapped[list["Cost"]] = relationship(
        back_populates="parameter", cascade="all, delete-orphan"
    )


class Cost(Base):
    __tablename__ = "mcp_cost"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parameter_id: Mapped[str] = mapped_column(
        ForeignKey("mcp_parameter.scenario_id", ondelete="CASCADE"), index=True
    )
    item: Mapped[str] = mapped_column(String(16))
    weeks: Mapped[int] = mapped_column(Integer)
    rate: Mapped[float] = mapped_column(Float)

    parameter: Mapped[Parameter] = relationship(back_populates="costs")


class Belt(Base):
    __tablename__ = "mcp_belt"

    sector_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    ore_id: Mapped[str] = mapped_column(String(8))
    deposit_amt: Mapped[int] = mapped_column(Integer)


class Team(Base):
    __tablename__ = "mcp_team"

    token: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    week: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    balance: Mapped[int] = mapped_column(Integer)


class Ledger(Base):
    __tablename__ = "mcp_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(
        ForeignKey("mcp_team.token", ondelete="CASCADE"), index=True
    )
    week: Mapped[int] = mapped_column(Integer)
    item: Mapped[str] = mapped_column(String(32))
    credit: Mapped[float] = mapped_column(Float)
    debit: Mapped[float] = mapped_column(Float)


class Hub(Base):
    __tablename__ = "mcp_hub"
    __table_args__ = (UniqueConstraint("team_id", "hub_id", name="uq_mcp_hub_team_hub"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("mcp_team.token", ondelete="CASCADE"))
    hub_id: Mapped[str] = mapped_column(String(8))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sector_id: Mapped[int] = mapped_column(Integer, default=-1)
    # Tonnes of accumulated ore for each ore type, for example {"X": 12726, "Y": 324}.
    amt: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    space_remaining: Mapped[int] = mapped_column(Integer, default=100)


class Site(Base):
    __tablename__ = "mcp_site"
    __table_args__ = (UniqueConstraint("team_id", "sector_id", name="uq_mcp_site_team_sector"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("mcp_team.token", ondelete="CASCADE"))
    sector_id: Mapped[int] = mapped_column(Integer)
    ore_id: Mapped[str] = mapped_column(String(8), default="X")
    deposit_amt: Mapped[int] = mapped_column(Integer)


class Order(Base):
    __tablename__ = "mcp_order"
    __table_args__ = (Index("ix_mcp_order_team_complete", "team_id", "complete"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("mcp_team.token", ondelete="CASCADE"))
    week: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(32))
    # Comma-separated lists, as the wire format returns them.
    hub_list: Mapped[str] = mapped_column(Text, default="")
    sector_id_list: Mapped[str] = mapped_column(Text, default="")
    ore_load: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    complete: Mapped[bool] = mapped_column(Boolean, default=False)
    insured: Mapped[bool] = mapped_column(Boolean, default=False)
    pirated: Mapped[bool] = mapped_column(Boolean, default=False)
