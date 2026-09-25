"""Home Connect API client with OAuth2 token management.

Home Connect (BSH) covers Bosch, Siemens, Gaggenau, NEFF, Thermador.
Docs: https://api-docs.home-connect.com/
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values, set_key

ENV_PATH = Path.home() / ".claude/.env"

AUTH_URL = "https://api.home-connect.com/security/oauth/authorize"
TOKEN_URL = "https://api.home-connect.com/security/oauth/token"
API_BASE = "https://api.home-connect.com/api"

ACCEPT_HEADER = "application/vnd.bsh.sdk.v1+json"

SCOPES = [
    "IdentifyAppliance",
    "Monitor",
    "Settings",
    "Control",
    "Dishwasher",
    "Oven",
    "Washer",
    "Dryer",
    "WasherDryer",
    "Refrigerator",
    "Freezer",
    "WineCooler",
    "CoffeeMaker",
    "Hob",
    "Hood",
    "CleaningRobot",
    "CookProcessor",
    "Microwave",
    "AirConditioner",
]


def _resolve_ca_bundle() -> str | bool:
    for var in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE"):
        v = os.environ.get(var)
        if v and Path(v).exists():
            return v
    merged = Path.home() / ".config/certs/bundle-with-cloudflare.pem"
    if merged.exists():
        return str(merged)
    for candidate in (
        "/etc/ssl/cert.pem",
        "/etc/ssl/certs/ca-certificates.crt",
        "/etc/pki/tls/certs/ca-bundle.crt",
    ):
        if Path(candidate).exists():
            return candidate
    return True


CA_BUNDLE = _resolve_ca_bundle()


class HomeConnectClient:
    def __init__(self) -> None:
        cfg = dotenv_values(ENV_PATH)
        self.client_id = cfg.get("HOMECONNECT_CLIENT_ID", "")
        self.client_secret = cfg.get("HOMECONNECT_CLIENT_SECRET", "")
        self.redirect_uri = cfg.get("HOMECONNECT_REDIRECT_URI", "http://localhost:8765/callback")
        self.access_token = cfg.get("HOMECONNECT_ACCESS_TOKEN", "") or ""
        self.refresh_token = cfg.get("HOMECONNECT_REFRESH_TOKEN", "") or ""
        expires_raw = cfg.get("HOMECONNECT_TOKEN_EXPIRES_AT", "") or "0"
        self.expires_at = int(expires_raw) if expires_raw.isdigit() else 0

        if not self.client_id or not self.client_secret:
            raise RuntimeError("HOMECONNECT_CLIENT_ID / HOMECONNECT_CLIENT_SECRET missing in .env")

    def _persist_tokens(self, token_response: dict[str, Any]) -> None:
        self.access_token = token_response["access_token"]
        if "refresh_token" in token_response:
            self.refresh_token = token_response["refresh_token"]
        self.expires_at = int(time.time()) + int(token_response.get("expires_in", 86400)) - 60

        set_key(str(ENV_PATH), "HOMECONNECT_ACCESS_TOKEN", self.access_token, quote_mode="never")
        set_key(str(ENV_PATH), "HOMECONNECT_REFRESH_TOKEN", self.refresh_token, quote_mode="never")
        set_key(str(ENV_PATH), "HOMECONNECT_TOKEN_EXPIRES_AT", str(self.expires_at), quote_mode="never")

    def exchange_code(self, code: str) -> None:
        with httpx.Client(timeout=30, verify=CA_BUNDLE) as client:
            r = client.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            r.raise_for_status()
            self._persist_tokens(r.json())

    def _reload_tokens_from_env(self) -> bool:
        """Pick up tokens another process (or a manual refresh) wrote to .env.

        BSH rotates the refresh token on every use, so a long-running daemon
        holding an old one in memory gets 400 invalid_grant. Returns True if
        .env had a different refresh token than the one in memory.
        """
        cfg = dotenv_values(ENV_PATH)
        refresh = cfg.get("HOMECONNECT_REFRESH_TOKEN", "") or ""
        if not refresh or refresh == self.refresh_token:
            return False
        self.refresh_token = refresh
        self.access_token = cfg.get("HOMECONNECT_ACCESS_TOKEN", "") or ""
        expires_raw = cfg.get("HOMECONNECT_TOKEN_EXPIRES_AT", "") or "0"
        self.expires_at = int(expires_raw) if expires_raw.isdigit() else 0
        return True

    def _post_refresh(self) -> httpx.Response:
        with httpx.Client(timeout=30, verify=CA_BUNDLE) as client:
            return client.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_secret": self.client_secret,
                },
            )

    def _refresh(self) -> None:
        # A newer, still-valid access token in .env means no refresh is needed.
        if self._reload_tokens_from_env() and self.access_token and time.time() < self.expires_at:
            return
        if not self.refresh_token:
            raise RuntimeError("No refresh token; run oauth.py to authorize.")
        r = self._post_refresh()
        if r.status_code == 400 and self._reload_tokens_from_env():
            r = self._post_refresh()
        r.raise_for_status()
        self._persist_tokens(r.json())

    def _ensure_token(self) -> None:
        if not self.access_token or time.time() >= self.expires_at:
            self._refresh()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        self._ensure_token()
        url = f"{API_BASE}{path}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": ACCEPT_HEADER,
        }
        if json is not None:
            headers["Content-Type"] = ACCEPT_HEADER
        with httpx.Client(timeout=30, verify=CA_BUNDLE) as client:
            r = client.request(method, url, params=params, json=json, headers=headers)
            if r.status_code == 401:
                self._refresh()
                headers["Authorization"] = f"Bearer {self.access_token}"
                r = client.request(method, url, params=params, json=json, headers=headers)
            if r.status_code >= 400:
                try:
                    body = r.json()
                except Exception:
                    body = r.text
                raise RuntimeError(f"Home Connect API {r.status_code}: {body}")
            if not r.content:
                return None
            ctype = r.headers.get("content-type", "")
            if "json" in ctype:
                return r.json()
            return r.text

    def get(self, path: str, **params: Any) -> Any:
        clean = {k: v for k, v in params.items() if v is not None}
        return self.request("GET", path, params=clean or None)

    def put(self, path: str, body: dict[str, Any]) -> Any:
        return self.request("PUT", path, json=body)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)
