"""Bot API under /mcp. Sprint 1 supplies /mcp/parameters only."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ol_musky.api.deps import Scenarios, Token
from ol_musky.api.envelope import McpError, envelope

router = APIRouter(prefix="/mcp")


@router.get("/parameters")
async def parameters(_token: Token, scenarios: Scenarios) -> JSONResponse:
    scenario = scenarios.current
    if scenario is None:
        raise McpError("parameters", 2200, "no scenario is loaded")
    return envelope("parameters", scenario.parameters_dict())
