"""Scenario persistence: Parameter, Cost, and Belt tables."""

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ol_musky.db.models import Belt, Cost, Parameter
from ol_musky.scenario import CostSpec, Scenario, ScenarioError, Sector


async def save_scenario(session: AsyncSession, scenario: Scenario) -> None:
    """Replace the stored scenario and belt. The database holds one scenario at a time."""
    await session.execute(delete(Belt))
    await session.execute(delete(Cost))
    await session.execute(delete(Parameter))

    session.add(
        Parameter(
            scenario_id=scenario.scenario_id,
            lifetime=scenario.lifetime,
            rows=scenario.rows,
            cols=scenario.cols,
            hub_capacity=scenario.hub_capacity,
            mining_rate=scenario.mining_rate,
            starting_capital=scenario.starting_capital,
            ms_per_week=scenario.ms_per_week,
            prospecting_offset=scenario.prospecting_offset,
            costs=[
                Cost(item=cost.item, weeks=cost.weeks, rate=cost.rate)
                for cost in scenario.costs.values()
            ],
        )
    )
    await session.execute(
        insert(Belt),
        [
            {"sector_id": sector_id, "ore_id": sector.ore_id, "deposit_amt": sector.deposit_amt}
            for sector_id, sector in enumerate(scenario.belt)
        ],
    )
    await session.commit()


async def load_scenario(session: AsyncSession, scenario_id: str | None = None) -> Scenario:
    """Read a scenario. With no scenario_id, the database must hold exactly one."""
    query = select(Parameter).options(selectinload(Parameter.costs))
    if scenario_id is not None:
        query = query.where(Parameter.scenario_id == scenario_id)
    parameters = (await session.execute(query)).scalars().all()

    if not parameters:
        raise ScenarioError(f"no such scenario_id ({scenario_id})")
    if len(parameters) > 1:
        raise ScenarioError("more than one scenario is stored; set OL_MUSKY_SCENARIO_ID")
    parameter = parameters[0]

    belt_rows = (await session.execute(select(Belt).order_by(Belt.sector_id))).scalars().all()
    return Scenario(
        scenario_id=parameter.scenario_id,
        lifetime=parameter.lifetime,
        rows=parameter.rows,
        cols=parameter.cols,
        hub_capacity=parameter.hub_capacity,
        mining_rate=parameter.mining_rate,
        starting_capital=parameter.starting_capital,
        ms_per_week=parameter.ms_per_week,
        prospecting_offset=parameter.prospecting_offset,
        costs={
            cost.item: CostSpec(item=cost.item, weeks=cost.weeks, rate=cost.rate)
            for cost in parameter.costs
        },
        belt=tuple(Sector(ore_id=row.ore_id, deposit_amt=row.deposit_amt) for row in belt_rows),
    )
