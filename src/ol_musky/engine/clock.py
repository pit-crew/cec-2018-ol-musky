"""Conversion of real time to MCP weeks."""

from datetime import datetime, timedelta


def week_at(start_time: datetime, now: datetime, ms_per_week: int) -> int:
    """Number of full MCP weeks between start_time and now."""
    return max(0, (now - start_time) // timedelta(milliseconds=ms_per_week))
