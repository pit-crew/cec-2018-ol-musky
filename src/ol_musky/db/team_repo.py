"""Team persistence: write-through of the live state to the mcp_* tables.

The live state in the World is the authority during a game. The database gets
the changes at intervals: new ledger entries and orders, changed order flags,
and the full set of hubs and sites for each team that changed.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ol_musky.db.models import Hub, Ledger, Order, Site, Team
from ol_musky.engine.state import TeamState
from ol_musky.world import World, hub_start_time


@dataclass
class _Stored:
    """What the database holds for one team."""

    ledger_count: int = 0
    order_ids: list[int] = field(default_factory=list)
    order_flags: list[tuple[bool, bool]] = field(default_factory=list)


@dataclass
class _Snapshot:
    token: str
    replace: bool
    team: dict[str, Any]
    ledger: list[dict[str, Any]]
    new_orders: list[dict[str, Any]]
    order_updates: list[tuple[int, dict[str, Any]]]  # (index in the team's order list, values)
    hubs: list[dict[str, Any]]
    sites: list[dict[str, Any]]


def _order_flags(order) -> tuple[bool, bool]:
    return (order.complete, order.pirated)


class TeamStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
        self._stored: dict[str, _Stored] = {}
        self._lock = asyncio.Lock()

    async def registered(self) -> list[tuple[str, str]]:
        """The (token, name) of each team in the database."""
        async with self._sessions() as session:
            rows = await session.execute(select(Team.token, Team.name).order_by(Team.name))
            return [(token, name) for token, name in rows]

    async def flush(self, world: World) -> int:
        """Write the changed teams to the database. Returns the number of teams written."""
        async with self._lock:
            tokens, stale = world.dirty, world.stale
            world.dirty, world.stale = set(), set()
            ms_per_week = world.scenario.ms_per_week if tokens else 0
            snapshots = [
                self._snapshot(world.teams[token], token in stale, ms_per_week)
                for token in tokens
                if token in world.teams
            ]
            if not snapshots:
                return 0
            try:
                async with self._sessions() as session:
                    for snapshot in snapshots:
                        await self._write(session, snapshot)
                    await session.commit()
            except Exception:
                # The stored rows are in an unknown condition: replace them on the next flush.
                world.dirty.update(tokens)
                world.stale.update(tokens)
                raise
            return len(snapshots)

    def _snapshot(self, team: TeamState, replace: bool, ms_per_week: int) -> _Snapshot:
        """Copy the changes of one team. This function does not await."""
        if replace or team.token not in self._stored:
            replace = True
            self._stored[team.token] = _Stored()
        stored = self._stored[team.token]
        token = team.token

        ledger = [
            {
                "team_id": token,
                "week": entry.week,
                "item": entry.item,
                "credit": entry.credit,
                "debit": entry.debit,
            }
            for entry in team.ledger[stored.ledger_count :]
        ]
        stored.ledger_count = len(team.ledger)

        known = len(stored.order_flags)
        order_updates = []
        for index, order in enumerate(team.orders[:known]):
            if _order_flags(order) != stored.order_flags[index]:
                stored.order_flags[index] = _order_flags(order)
                order_updates.append(
                    (index, {"complete": order.complete, "pirated": order.pirated})
                )
        new_orders = []
        for order in team.orders[known:]:
            stored.order_flags.append(_order_flags(order))
            new_orders.append(
                {
                    "team_id": token,
                    "week": order.week,
                    "action": order.action,
                    "hub_list": ",".join(order.hub_ids),
                    "sector_id_list": ",".join(map(str, order.sector_ids)),
                    "ore_load": dict(order.ore_load),
                    "complete": order.complete,
                    "insured": order.insured,
                    "pirated": order.pirated,
                }
            )

        return _Snapshot(
            token=token,
            replace=replace,
            team={
                "token": token,
                "name": team.name,
                "week": team.week,
                "start_time": team.start_time,
                "balance": team.balance,
            },
            ledger=ledger,
            new_orders=new_orders,
            order_updates=order_updates,
            hubs=[
                {
                    "team_id": token,
                    "hub_id": hub.hub_id,
                    "start_time": hub_start_time(team, hub, ms_per_week),
                    "sector_id": hub.sector_id,
                    "amt": dict(hub.amt),
                    "active": hub.active,
                    "space_remaining": hub.space_remaining,
                }
                for hub in team.hubs.values()
            ],
            sites=[
                {
                    "team_id": token,
                    "sector_id": sector_id,
                    "ore_id": site.ore_id,
                    "deposit_amt": site.deposit_amt,
                }
                for sector_id, site in team.sites.items()
            ],
        )

    async def _write(self, session: AsyncSession, snapshot: _Snapshot) -> None:
        token = snapshot.token
        stored = self._stored[token]

        team_insert = sqlite_insert(Team).values(snapshot.team)
        await session.execute(
            team_insert.on_conflict_do_update(
                index_elements=[Team.token],
                set_={key: value for key, value in snapshot.team.items() if key != "token"},
            )
        )

        if snapshot.replace:
            await session.execute(delete(Ledger).where(Ledger.team_id == token))
            await session.execute(delete(Order).where(Order.team_id == token))
        await session.execute(delete(Hub).where(Hub.team_id == token))
        await session.execute(delete(Site).where(Site.team_id == token))

        if snapshot.ledger:
            await session.execute(insert(Ledger), snapshot.ledger)
        for index, values in snapshot.order_updates:
            await session.execute(
                update(Order).where(Order.id == stored.order_ids[index]).values(values)
            )
        for row in snapshot.new_orders:
            result = await session.execute(insert(Order).values(row))
            stored.order_ids.append(result.inserted_primary_key[0])
        if snapshot.hubs:
            await session.execute(insert(Hub), snapshot.hubs)
        if snapshot.sites:
            await session.execute(insert(Site), snapshot.sites)


async def add_team(session: AsyncSession, token: str, name: str, team: dict[str, Any]) -> None:
    """Store a team registration. An existing team with the token is replaced."""
    await session.execute(delete(Team).where(Team.token == token))
    await session.execute(insert(Team).values(token=token, name=name, **team))
    await session.commit()
