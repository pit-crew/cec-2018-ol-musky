"""Belt files: save a belt, list the saved belts, and select the belt of the scenario.

A belt file is a CSV file in the directory of the scenario file, with one line
`ore,deposit` for each sector. Lines that start with `#` are comments; a belt
that the generator made has its seed and its specification there, so that the
same belt can be made again.

The scenario file names the belt that the server loads when it starts.
`select_belt` changes only that name in the scenario file.
"""

import json
import re
from dataclasses import asdict
from pathlib import Path

import yaml

from ol_musky.belt import BeltSpec
from ol_musky.scenario import read_belt, read_scenario
from ol_musky.world import Asteroid

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}")
_FILE_LINE = re.compile(r"^(?P<indent>[ \t]+)file:[ \t]*(?P<name>\S+)(?P<rest>.*)$", re.MULTILINE)


class BeltFileError(Exception):
    """A belt file request is not valid."""


def _path(directory: Path, name: str) -> Path:
    if not _NAME.fullmatch(name):
        raise BeltFileError("a belt name has 40 or fewer letters, digits, '-' and '_'")
    return directory / f"{name}.csv"


def save_belt(
    directory: Path, name: str, belt: tuple[Asteroid, ...], spec: BeltSpec, seed: int
) -> Path:
    """Write a generated belt to `<name>.csv`. A file that exists is not replaced."""
    path = _path(directory, name)
    if path.exists():
        raise BeltFileError(f"the belt '{name}' exists; use a different name")
    lines = [
        "# ol-musky belt",
        f"# seed: {seed}",
        f"# spec: {json.dumps(asdict(spec))}",
        *(f"{asteroid.ore},{asteroid.deposit}" for asteroid in belt),
    ]
    path.write_text("\n".join(lines) + "\n")
    return path


def origin(path: Path) -> dict | None:
    """The seed and the specification of a generated belt file, or None for other files."""
    found = {}
    with path.open() as lines:
        for line in lines:
            if not line.startswith("#"):
                break
            key, _, value = line[1:].partition(":")
            found[key.strip()] = value.strip()
    if "seed" not in found or "spec" not in found:
        return None
    return {"seed": int(found["seed"]), "spec": json.loads(found["spec"])}


def belt_names(directory: Path) -> list[str]:
    """The names of the belt files in the directory."""
    return sorted(path.stem for path in directory.glob("*.csv") if _NAME.fullmatch(path.stem))


def load_belt(directory: Path, name: str) -> tuple[Asteroid, ...]:
    path = _path(directory, name)
    if not path.exists():
        raise BeltFileError(f"there is no belt '{name}'")
    return read_belt(path)


def selected_belt(scenario_path: Path) -> str:
    """The name of the belt that the scenario file loads."""
    return Path(yaml.safe_load(scenario_path.read_text())["belt"]["file"]).stem


def select_belt(scenario_path: Path, name: str) -> None:
    """Make the belt the one that the server loads when it starts.

    Only the belt file name in the scenario file changes; the comments and all
    other lines stay. The belt must have the size of the scenario.
    """
    belt = load_belt(scenario_path.parent, name)
    cfg = yaml.safe_load(scenario_path.read_text())["belt"]
    if len(belt) != cfg["rows"] * cfg["cols"]:
        raise BeltFileError(
            f"the belt '{name}' has {len(belt)} sectors; "
            f"the scenario needs {cfg['rows']} x {cfg['cols']}"
        )
    before = scenario_path.read_text()
    after, changes = _FILE_LINE.subn(rf"\g<indent>file: {name}.csv\g<rest>", before, count=1)
    if changes != 1:
        raise BeltFileError(f"{scenario_path.name} has no belt file line")
    scenario_path.write_text(after)
    try:
        read_scenario(scenario_path)
    except Exception as error:
        scenario_path.write_text(before)
        raise BeltFileError(
            f"the scenario does not load with the belt '{name}': {error}"
        ) from error
