"""Request dependencies."""

from typing import Annotated

from fastapi import Depends, Query, Request

from ol_musky.api.envelope import McpError
from ol_musky.scenario import ScenarioStore

MAX_TOKEN_LENGTH = 32


def _is_clean(value: str) -> bool:
    return all(char.isalnum() or char in "-_" for char in value)


def require_token(token: Annotated[str | None, Query()] = None) -> str:
    """Check the format of the `token` query parameter (status codes 1000 and 1001)."""
    if token is None:
        raise McpError("validation", 1001, "token required - see competition coordinator")
    if len(token) > MAX_TOKEN_LENGTH or not _is_clean(token):
        raise McpError("validation", 1000, "token must be 32 or fewer alpha-numerics")
    return token


def get_scenario_store(request: Request) -> ScenarioStore:
    return request.app.state.scenarios


Token = Annotated[str, Depends(require_token)]
Scenarios = Annotated[ScenarioStore, Depends(get_scenario_store)]
