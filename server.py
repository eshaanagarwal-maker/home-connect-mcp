"""Home Connect MCP server — Bosch / Siemens / Gaggenau / NEFF / Thermador appliances.

Exposes the BSH Home Connect REST API as MCP tools over stdio.

Safety note: BSH firmware blocks remote start of wet/hot programs unless
"Remote Start" has been physically armed on the appliance within the last
~24h (or per-cycle, depending on model). `start_program` will return an error
like `SDK.Error.WrongOperationState` until that's done at the unit.
"""
from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from home_connect_client import HomeConnectClient

mcp = FastMCP("home-connect")
_client: HomeConnectClient | None = None


def client() -> HomeConnectClient:
    global _client
    if _client is None:
        _client = HomeConnectClient()
    return _client


def _fmt(value: Any) -> str:
    return json.dumps(value, indent=2, default=str)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

@mcp.tool()
def list_appliances() -> str:
    """List every Home Connect appliance paired to this account.

    Returns each appliance's haId (used by every other tool), name, brand,
    type (Dishwasher, Oven, etc.), vib (model code), connected status.
    """
    return _fmt(client().get("/homeappliances"))


@mcp.tool()
def get_appliance(ha_id: str) -> str:
    """Return full details for one appliance.

    Args:
        ha_id: The haId from list_appliances. BSH returns this as a long numeric
            string, e.g. "263060527860003497" — NOT a brand/model/MAC composite.
            Always call list_appliances first to get the real haId; passing a
            made-up string returns 403 insufficient_scope (BSH doesn't reveal
            whether unknown haIds exist).
    """
    return _fmt(client().get(f"/homeappliances/{ha_id}"))


# ---------------------------------------------------------------------------
# Status & monitoring
# ---------------------------------------------------------------------------

@mcp.tool()
def get_status(ha_id: str) -> str:
    """Read all current status values: door state, operation state, remote start enabled, etc."""
    return _fmt(client().get(f"/homeappliances/{ha_id}/status"))


@mcp.tool()
def get_settings(ha_id: str) -> str:
    """Read all current settings: power state, child lock, ambient lighting, etc."""
    return _fmt(client().get(f"/homeappliances/{ha_id}/settings"))


@mcp.tool()
def get_active_program(ha_id: str) -> str:
    """Return the currently running program with its remaining time + progress.

    Returns 404 if no program is active.
    """
    return _fmt(client().get(f"/homeappliances/{ha_id}/programs/active"))


@mcp.tool()
def get_selected_program(ha_id: str) -> str:
    """Return the program currently selected on the appliance dial (not yet started)."""
    return _fmt(client().get(f"/homeappliances/{ha_id}/programs/selected"))


# ---------------------------------------------------------------------------
# Programs
# ---------------------------------------------------------------------------

@mcp.tool()
def list_available_programs(ha_id: str) -> str:
    """List all programs this appliance supports (Eco, Auto, Intensive, etc.)."""
    return _fmt(client().get(f"/homeappliances/{ha_id}/programs/available"))


@mcp.tool()
def get_program_options(ha_id: str, program_key: str) -> str:
    """List the configurable options for a specific program (delay, extra dry, etc.).

    Args:
        ha_id: The haId.
        program_key: Full program key e.g. "Dishcare.Dishwasher.Program.Eco50".
    """
    return _fmt(client().get(f"/homeappliances/{ha_id}/programs/available/{program_key}"))


@mcp.tool()
def select_program(ha_id: str, program_key: str, options: list[dict] | None = None) -> str:
    """Pre-select a program on the appliance (does NOT start it).

    Args:
        ha_id: The haId.
        program_key: e.g. "Dishcare.Dishwasher.Program.Eco50".
        options: Optional list of {"key": "...", "value": ...} dicts.
    """
    body = {"data": {"key": program_key, "options": options or []}}
    return _fmt(client().put(f"/homeappliances/{ha_id}/programs/selected", body))


@mcp.tool()
def start_program(ha_id: str, program_key: str, options: list[dict] | None = None) -> str:
    """Start a program. REQUIRES Remote Start to be armed on the physical appliance.

    Args:
        ha_id: The haId.
        program_key: e.g. "Dishcare.Dishwasher.Program.Eco50".
        options: Optional list of {"key": "...", "value": ...} dicts.

    Common options for Dishwasher:
      - BSH.Common.Option.StartInRelative (seconds, for delayed start)
      - Dishcare.Dishwasher.Option.IntensivZone
      - Dishcare.Dishwasher.Option.HygienePlus
      - Dishcare.Dishwasher.Option.ExtraDry
    """
    body = {"data": {"key": program_key, "options": options or []}}
    return _fmt(client().put(f"/homeappliances/{ha_id}/programs/active", body))


@mcp.tool()
def stop_program(ha_id: str) -> str:
    """Abort the currently running program."""
    return _fmt(client().delete(f"/homeappliances/{ha_id}/programs/active"))


# ---------------------------------------------------------------------------
# Commands & settings
# ---------------------------------------------------------------------------

@mcp.tool()
def list_commands(ha_id: str) -> str:
    """List commands this appliance accepts (pause, resume, etc.)."""
    return _fmt(client().get(f"/homeappliances/{ha_id}/commands"))


@mcp.tool()
def send_command(ha_id: str, command_key: str, value: Any = True) -> str:
    """Send a one-shot command (e.g. BSH.Common.Command.PauseProgram).

    Args:
        ha_id: The haId.
        command_key: Full command key.
        value: Usually True. Defaults to True.
    """
    body = {"data": {"key": command_key, "value": value}}
    return _fmt(client().put(f"/homeappliances/{ha_id}/commands/{command_key}", body))


@mcp.tool()
def set_setting(ha_id: str, setting_key: str, value: Any) -> str:
    """Update one setting (e.g. BSH.Common.Setting.PowerState -> 'BSH.Common.EnumType.PowerState.On').

    Args:
        ha_id: The haId.
        setting_key: e.g. "BSH.Common.Setting.ChildLock".
        value: The new value (string, bool, or number depending on the setting).
    """
    body = {"data": {"key": setting_key, "value": value}}
    return _fmt(client().put(f"/homeappliances/{ha_id}/settings/{setting_key}", body))


if __name__ == "__main__":
    mcp.run()
