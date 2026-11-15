"""The admin functions of the server, under /admin.

Access: if the server has an admin key, each request must give it as `key`.
With no admin key, only requests from the computer of the server are permitted.

Belt functions:
- preview a belt from a specification and a seed
- save a previewed belt as a CSV file in the directory of the scenario file
- list the saved belts
- select the belt that the server loads when it starts
"""

import hmac
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ol_musky import belt_files
from ol_musky.belt import BeltSpec, make_belt, measure
from ol_musky.belt_files import BeltFileError
from ol_musky.scenario import Scenario
from ol_musky.world import Asteroid

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
PAGES = Path(__file__).parent / "pages"
_DEFAULT = BeltSpec()


def allow(request: Request, key: Annotated[str | None, Query()] = None) -> None:
    wanted = request.app.state.admin_key
    if wanted:
        permitted = key is not None and hmac.compare_digest(key, wanted)
    else:
        permitted = request.client is not None and request.client.host in LOCAL_HOSTS
    if not permitted:
        raise HTTPException(403, "admin access is not permitted")


router = APIRouter(prefix="/admin", dependencies=[Depends(allow)])


def get_scenario(request: Request) -> Scenario:
    return request.app.state.league.scenario


def get_scenario_path(request: Request) -> Path:
    path = request.app.state.scenario_path
    if path is None:
        raise HTTPException(503, "the server has no scenario file")
    return path


ActiveScenario = Annotated[Scenario, Depends(get_scenario)]
ScenarioPath = Annotated[Path, Depends(get_scenario_path)]


class SpecFields(BaseModel):
    """The settings of a belt that the admin can change. The size comes from the scenario."""

    clusters: int = _DEFAULT.clusters
    cluster_size: float = _DEFAULT.cluster_size
    coverage: float = _DEFAULT.coverage
    total_ore: int = _DEFAULT.total_ore
    y_share: float = _DEFAULT.y_share
    roughness: float = _DEFAULT.roughness
    seed: int = 1

    def spec(self, scenario: Scenario) -> BeltSpec:
        fields = self.model_dump(exclude={"seed", "name"})
        rows = len(scenario.asteroids) // scenario.cols
        try:
            return BeltSpec(rows=rows, cols=scenario.cols, **fields)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error


class SaveFields(SpecFields):
    name: str


class SelectFields(BaseModel):
    name: str


def view(belt: tuple[Asteroid, ...], scenario: Scenario) -> dict:
    """A belt for the page: its ore, its deposits, and its measurements."""
    report = measure(belt, scenario.cols, scenario.rate, scenario.terms.hub_capacity)
    return {
        "rows": len(belt) // scenario.cols,
        "cols": scenario.cols,
        "ores": "".join(asteroid.ore for asteroid in belt),
        "deposits": [asteroid.deposit for asteroid in belt],
        "report": asdict(report),
    }


def _fail(error: BeltFileError) -> HTTPException:
    return HTTPException(400, str(error))


@router.get("", include_in_schema=False)
async def admin_page() -> FileResponse:
    return FileResponse(PAGES / "admin.html", media_type="text/html")


@router.get("/belt/preview")
async def preview(fields: Annotated[SpecFields, Query()], scenario: ActiveScenario) -> dict:
    """The belt of the settings and the seed. Nothing is saved."""
    spec = fields.spec(scenario)
    return {
        **view(make_belt(spec, fields.seed), scenario),
        "seed": fields.seed,
        "spec": asdict(spec),
    }


@router.post("/belt/save")
async def save(fields: SaveFields, scenario: ActiveScenario, path: ScenarioPath) -> dict:
    """Save the belt of the settings and the seed as `<name>.csv`."""
    spec = fields.spec(scenario)
    try:
        saved = belt_files.save_belt(
            path.parent, fields.name, make_belt(spec, fields.seed), spec, fields.seed
        )
    except BeltFileError as error:
        raise _fail(error) from error
    return {"saved": saved.name}


@router.get("/belts")
async def belts(request: Request, scenario: ActiveScenario, path: ScenarioPath) -> dict:
    """The saved belts. `loaded` is in use now; `selected` loads at the next start."""
    sectors = len(scenario.asteroids)
    listing = []
    for name in belt_files.belt_names(path.parent):
        try:
            belt = belt_files.load_belt(path.parent, name)
        except (BeltFileError, ValueError):
            continue  # not a belt file
        fits = len(belt) == sectors
        listing.append(
            {
                "name": name,
                "sectors": len(belt),
                "fits": fits,
                "origin": belt_files.origin(path.parent / f"{name}.csv"),
                "report": view(belt, scenario)["report"] if fits else None,
            }
        )
    return {
        "loaded": request.app.state.loaded_belt,
        "selected": belt_files.selected_belt(path),
        "belts": listing,
    }


@router.get("/belt/saved")
async def saved(name: str, scenario: ActiveScenario, path: ScenarioPath) -> dict:
    """A saved belt, for the preview."""
    try:
        belt = belt_files.load_belt(path.parent, name)
    except BeltFileError as error:
        raise _fail(error) from error
    if len(belt) != len(scenario.asteroids):
        raise HTTPException(400, f"the belt '{name}' does not have the size of the scenario")
    return {**view(belt, scenario), "name": name}


@router.post("/belt/select")
async def select(fields: SelectFields, path: ScenarioPath) -> dict:
    """Select the belt that the server loads when it starts."""
    try:
        belt_files.select_belt(path, fields.name)
    except BeltFileError as error:
        raise _fail(error) from error
    return {"selected": fields.name}
