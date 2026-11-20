"""Stdio MCP. Credentials come from this repo's .env, not the launching workspace."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from mcp.server.mcpserver import MCPServer

from custom_components.skola24.api import (
    get_temporary_change,
    get_timetable,
    list_children,
    set_temporary_change_message,
)
from custom_components.skola24.auth import Credentials
from custom_components.skola24.client import Skola24Client
from custom_components.skola24.const import DEFAULT_HOST

ROOT = Path(__file__).resolve().parent
INSTRUCTIONS = (
    "Skola24 is the Swedish school platform used by Gävle kommun (gavle.skola24.se). "
    "This MCP logs in as a vårdnadshavare. "
    "Use it for Schemavisaren (get_timetable) and Tillfällig ändring "
    "(get_temporary_change, set_temporary_change_message). "
    "set_temporary_change_message writes a meddelande for one child and one day and does not change clock times. "
    "list_children lists the kids on the account. Dates are Europe/Stockholm. Default day/week is today. "
    "This is not frånvaro, not ledighetsansökan, not a new vistelsetid schema."
)

mcp = MCPServer("skola24", instructions=INSTRUCTIONS)
_client: Skola24Client | None = None


def _load_env() -> None:
    path = ROOT / ".env"
    try:
        text = path.read_text()
    except OSError:
        return
    for line in text.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#") or "=" not in trimmed:
            continue
        key, value = trimmed.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key.strip()] = value


def _client_or_create() -> Skola24Client:
    global _client
    if _client is not None:
        return _client
    _load_env()
    username = os.environ.get("USERNAME", "").strip()
    password = os.environ.get("PASSWORD", "").strip()
    if not username or not password:
        raise RuntimeError("Missing USERNAME or PASSWORD in .env")
    host = os.environ.get("SKOLA24_HOST", "").strip() or DEFAULT_HOST
    session = os.environ.get("SKOLA24_SESSION", "").strip()
    session_path = Path(session) if session else ROOT / "data" / "session.json"
    _client = Skola24Client(
        Credentials(username=username, password=password, host=host),
        session_path,
    )
    return _client


def _dump(value) -> str:
    if isinstance(value, list):
        payload = [asdict(item) for item in value]
    else:
        payload = asdict(value)
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool(name="list_children")
async def list_children_tool() -> str:
    """List children (barn) on this Skola24 parent account for Gävle schools. Use the names with get_timetable, get_temporary_change, or set_temporary_change_message."""
    return _dump(await list_children(_client_or_create()))


@mcp.tool(name="get_timetable")
async def get_timetable_tool(
    child: str | None = None,
    date: str | None = None,
    week: int | None = None,
    year: int | None = None,
) -> str:
    """Schemavisaren: published school timetable for one child and one ISO week. Not fritids. Defaults to the week of today (Europe/Stockholm). child is required when several children exist. date is YYYY-MM-DD and overrides week/year."""
    result = await get_timetable(
        _client_or_create(),
        child=child,
        date=date,
        week=week,
        year=year,
    )
    return _dump(result)


@mcp.tool(name="get_temporary_change")
async def get_temporary_change_tool(child: str, date: str | None = None) -> str:
    """Tillfällig ändring: today's meddelande and vistelsetid for one child. message is null when none. exception_times are temporary drop-off/pick-up. ordinary_times are normal care hours. date is YYYY-MM-DD, default today (Europe/Stockholm)."""
    return _dump(await get_temporary_change(_client_or_create(), child, date))


@mcp.tool(name="set_temporary_change_message")
async def set_temporary_change_message_tool(
    child: str,
    message: str,
    date: str | None = None,
) -> str:
    """Tillfällig ändring: send a meddelande to preschool/fritids for one child and one day. Does not change clock times. Overwrites any existing message. date is YYYY-MM-DD, default today. Empty message clears the day's meddelande."""
    return _dump(
        await set_temporary_change_message(_client_or_create(), child, message, date)
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
