"""MCP wire envelope: {"<action>": <data>, "status": <code>, "description": <text>}.

The MCP reports all errors in the envelope with HTTP 200, as the Django application did.
"""

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


def envelope(action: str, data: Any, status: int = 0, description: str = "") -> JSONResponse:
    return JSONResponse({action: data, "status": status, "description": description})


class McpError(Exception):
    """Stops a request and returns an error envelope."""

    def __init__(self, action: str, status: int, description: str, data: Any = None) -> None:
        super().__init__(description)
        self.action = action
        self.status = status
        self.description = description
        self.data = {} if data is None else data


async def mcp_error_handler(_request: Request, exc: McpError) -> JSONResponse:
    return envelope(exc.action, exc.data, exc.status, exc.description)
