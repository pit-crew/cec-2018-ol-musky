"""Wire formats of the team data in the MCP responses."""

import json
from typing import Any

from ol_musky.engine.state import Hub, LedgerEntry, Order, TeamState
from ol_musky.scenario import Scenario
from ol_musky.world import hub_start_time


def team_dict(team: TeamState) -> dict[str, Any]:
    return {
        "token": team.token,
        "name": team.name,
        "week": team.week,
        "start_time": str(team.start_time),
        # The balance is exact internally. The wire value is an integer, rounded down.
        "balance": int(team.balance // 1),
    }


def hub_dict(team: TeamState, hub: Hub, scenario: Scenario) -> dict[str, Any]:
    return {
        "hub_id": hub.hub_id,
        "start_time": str(hub_start_time(team, hub, scenario.ms_per_week)),
        "sector_id": hub.sector_id,
        # A JSON document in a string: clients call json.loads on it.
        "amt": json.dumps(hub.amt),
        "space_remaining": hub.space_remaining,
        "active": hub.active,
    }


def order_dict(order: Order) -> dict[str, Any]:
    return {
        "week": order.week,
        "action": order.action,
        "hub_list": ",".join(order.hub_ids),
        "sector_id_list": ",".join(map(str, order.sector_ids)),
        "ore_load": json.dumps(order.ore_load),
        "complete": order.complete,
    }


def ledger_dict(entry: LedgerEntry) -> dict[str, Any]:
    return {"week": entry.week, "item": entry.item, "credit": entry.credit, "debit": entry.debit}


def session_dict(team: TeamState, scenario: Scenario, orders_key: str = "orders") -> dict[str, Any]:
    """Team, hubs, and pending orders. /mcp/startup uses the key `pending_orders`."""
    return {
        "team": team_dict(team),
        "hubs": {hub.hub_id: hub_dict(team, hub, scenario) for hub in team.hubs.values()},
        orders_key: [order_dict(order) for order in team.pending_orders()],
    }
