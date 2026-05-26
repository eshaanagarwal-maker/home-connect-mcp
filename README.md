# home-connect-mcp

Read + control Bosch / Siemens / Gaggenau / NEFF / Thermador appliances
paired to a single Home Connect account, via the official BSH REST API.

## Setup

```bash
cd ~/Code/home-connect-mcp
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install mcp httpx python-dotenv

# Fill .env with HOMECONNECT_CLIENT_ID + HOMECONNECT_CLIENT_SECRET first
# (from https://developer.home-connect.com → Your Applications), then:
venv/bin/python oauth.py
```

`oauth.py` opens your browser, you approve the consent screen, the local
listener on `localhost:8765` catches the redirect, and tokens land in `.env`.

## Tools exposed

| Tool | What it does |
|---|---|
| `list_appliances` | All paired appliances on the account |
| `get_appliance` | One appliance's metadata |
| `get_status` | Door state, operation state, remote-start armed, etc. |
| `get_settings` | Power state, child lock, ambient light |
| `get_active_program` | What's running right now |
| `get_selected_program` | What's queued on the dial |
| `list_available_programs` | Programs this appliance supports |
| `get_program_options` | Configurable options for one program |
| `select_program` | Pre-select a program (does NOT start) |
| `start_program` | Start a program (needs Remote Start armed on unit) |
| `stop_program` | Abort the active program |
| `list_commands` | Available commands (Pause, Resume...) |
| `send_command` | Send one (e.g. BSH.Common.Command.PauseProgram) |
| `set_setting` | Update one setting |

## Safety constraints baked into BSH firmware

Even though the API exposes a `start_program` endpoint, BSH firmware blocks
remote starts of wet/hot programs unless **Remote Start** is physically
armed on the appliance. Typical flow:

1. Load the dishwasher.
2. Press and hold the Remote Start button until the LED is solid.
3. Now `select_program` + `start_program` from Claude will succeed.
4. The arm-state typically clears after one cycle or ~24h.

Reads (`get_status`, `get_active_program`, etc.) work whenever the
appliance is powered and connected to WiFi.

## Token lifecycle

- Access tokens expire after ~24h.
- Refresh happens automatically on first 401.
- Refresh tokens are long-lived; do **not** share between machines (BSH
  rotates rapidly; sharing causes lockouts similar to the Whoop pattern).
