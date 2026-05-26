"""One-time OAuth2 authorization for Home Connect.

Run:  venv/bin/python oauth.py

Opens the Home Connect consent page, starts a local listener on
localhost:8765, receives the authorization code, exchanges it for tokens,
and persists access_token + refresh_token into .env.
"""
from __future__ import annotations

import secrets
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from home_connect_client import AUTH_URL, SCOPES, HomeConnectClient


class _Handler(BaseHTTPRequestHandler):
    received_code: str | None = None
    expected_state: str = ""

    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        state = qs.get("state", [""])[0]
        code = qs.get("code", [""])[0]
        if state != _Handler.expected_state or not code:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"State mismatch or missing code. Close this window and retry.")
            return
        _Handler.received_code = code
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body style='font-family:sans-serif;padding:40px'>"
            b"<h2>Home Connect authorized.</h2>"
            b"<p>You can close this tab and return to your terminal.</p>"
            b"</body></html>"
        )


def main() -> int:
    client = HomeConnectClient()
    state = secrets.token_urlsafe(16)
    _Handler.expected_state = state

    auth_params = {
        "response_type": "code",
        "client_id": client.client_id,
        "redirect_uri": client.redirect_uri,
        "scope": " ".join(SCOPES),
        "state": state,
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(auth_params)}"
    print("Opening browser to authorize Home Connect...")
    print(f"If it doesn't open, visit:\n  {url}\n")
    webbrowser.open(url)

    server = HTTPServer(("127.0.0.1", 8765), _Handler)
    try:
        while _Handler.received_code is None:
            server.handle_request()
    finally:
        server.server_close()

    print("Authorization code received. Exchanging for tokens...")
    client.exchange_code(_Handler.received_code)
    print("Done. Access + refresh tokens written to .env.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
