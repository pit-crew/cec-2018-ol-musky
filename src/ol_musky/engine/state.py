"""In-memory state of one team."""

from dataclasses import dataclass, field
from datetime import datetime

UNDEPLOYED = -1

# Order actions
DELIVER_HUBS = "deliver_hubs"
RELOCATE_HUBS = "relocate_hubs"
SHIP_AND_SELL_ORE = "ship and sell ore"


@dataclass
class LedgerEntry:
    week: int
    item: str
    credit: float = 0.0
    debit: float = 0.0


@dataclass
class Hub:
    hub_id: str
    sector_id: int = UNDEPLOYED
    amt: dict[str, int] = field(default_factory=dict)  # tonnes for each ore type
    active: bool = False
    space_remaining: int = 100  # percent
    mined_through: int = 0  # the last week for which mining is complete

    @property
    def deployed(self) -> bool:
        return self.sector_id != UNDEPLOYED


@dataclass
class Site:
    """A team's view of one sector that its bots can mine."""

    ore_id: str
    deposit_amt: int


@dataclass
class Order:
    week: int  # the week in which the order completes
    action: str
    hub_ids: tuple[str, ...] = ()
    sector_ids: tuple[int, ...] = ()
    ore_load: dict[str, int] = field(default_factory=dict)
    complete: bool = False
    insured: bool = False
    pirated: bool = False


@dataclass
class TeamState:
    token: str
    name: str
    start_time: datetime
    balance: float  # millions of dollars
    week: int = 0
    ledger: list[LedgerEntry] = field(default_factory=list)
    hubs: dict[str, Hub] = field(default_factory=dict)
    sites: dict[int, Site] = field(default_factory=dict)  # key is the sector ID
    orders: list[Order] = field(default_factory=list)

    def credit(self, item: str, amount: float) -> None:
        self.balance += amount
        self.ledger.append(LedgerEntry(week=self.week, item=item, credit=amount))

    def debit(self, item: str, amount: float) -> None:
        self.balance -= amount
        self.ledger.append(LedgerEntry(week=self.week, item=item, debit=amount))

    def pending_orders(self, action: str | None = None) -> list[Order]:
        return [
            order
            for order in self.orders
            if not order.complete and (action is None or order.action == action)
        ]
