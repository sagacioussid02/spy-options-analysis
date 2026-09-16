"""
Chunk 3, step 1 of 2 — ONE-TIME Robinhood OAuth capture.

CMA can refresh tokens but cannot run the interactive browser handshake. So we
do that handshake here, once, on your machine, and save the resulting tokens to
cma_lab/.env. After this, CMA's vault keeps them fresh automatically.

This is a standard MCP-spec OAuth flow against Robinhood's published endpoints:
    1. Discover the authorization server metadata.
    2. Dynamic Client Registration (DCR) -> mint a client_id (public client).
    3. PKCE (S256) authorization-code flow via a localhost loopback redirect.
    4. Exchange the code for access_token + refresh_token at the token endpoint.

Run it:
    .venv/bin/python cma_lab/chunk3_get_robinhood_token.py

A browser opens to Robinhood. Log in (if needed) and authorize the AGENTIC
account. The tab will say it's safe to close, and tokens land in cma_lab/.env.

Prereq: you must already have created a Robinhood agentic trading account
(robinhood.com -> Agentic Trading). The authorize screen targets that account.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

MCP_URL = "https://agent.robinhood.com/mcp/trading"
AS_METADATA_URL = "https://agent.robinhood.com/.well-known/oauth-authorization-server"
REDIRECT_PORT = 8765
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
SCOPE = "internal"
ENV_PATH = Path(__file__).parent / ".env"


def _http_json(url: str, *, data: bytes | None = None, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise SystemExit(f"HTTP {e.code} from {url}\n{body}") from None


def discover() -> dict:
    print(f"[1/4] discovering OAuth metadata: {AS_METADATA_URL}")
    return _http_json(AS_METADATA_URL)


def register_client(registration_endpoint: str) -> str:
    print(f"[2/4] registering a client (DCR): {registration_endpoint}")
    body = json.dumps({
        "client_name": "spy-cma-lab",
        "redirect_uris": [REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": SCOPE,
    }).encode()
    reg = _http_json(registration_endpoint, data=body, headers={"Content-Type": "application/json"})
    cid = reg.get("client_id")
    if not cid:
        raise SystemExit(f"Registration returned no client_id: {reg}")
    print(f"      client_id = {cid}")
    return cid


def make_pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


_captured: dict = {}


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        _captured["code"] = params.get("code", [None])[0]
        _captured["state"] = params.get("state", [None])[0]
        _captured["error"] = params.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h2>Robinhood authorization received.</h2><p>You can close this tab.</p>")

    def log_message(self, *args):  # silence the default request logging
        pass


def authorize(authorization_endpoint: str, client_id: str) -> tuple[str, str]:
    verifier, challenge = make_pkce()
    state = secrets.token_urlsafe(16)
    url = authorization_endpoint + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": MCP_URL,
    })
    print(f"[3/4] opening browser to authorize:\n      {url}")
    print("      (waiting for Robinhood to redirect back to localhost — finish "
          "funding/authorizing in the browser; this will keep waiting)")
    server = HTTPServer(("localhost", REDIRECT_PORT), _CallbackHandler)
    webbrowser.open(url)
    # Keep serving until we actually capture the code (or an error). This ignores
    # stray hits to the callback port (favicon, prefetch) that aren't /callback.
    while _captured.get("code") is None and _captured.get("error") is None:
        server.handle_request()
    server.server_close()

    if _captured.get("error"):
        raise SystemExit(f"Authorization error: {_captured['error']}")
    if _captured.get("state") != state:
        raise SystemExit("State mismatch — possible CSRF, aborting.")
    code = _captured.get("code")
    if not code:
        raise SystemExit("No authorization code returned.")
    return code, verifier


def exchange(token_endpoint: str, client_id: str, code: str, verifier: str) -> dict:
    print(f"[4/4] exchanging code for tokens: {token_endpoint}")
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "code_verifier": verifier,
        "resource": MCP_URL,
    }).encode()
    return _http_json(token_endpoint, data=data,
                      headers={"Content-Type": "application/x-www-form-urlencoded"})


def update_env(values: dict) -> None:
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    seen = set()
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in values:
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, val in values.items():
        if key not in seen:
            out.append(f"{key}={val}")
    ENV_PATH.write_text("\n".join(out) + "\n")


def main() -> None:
    meta = discover()
    client_id = register_client(meta["registration_endpoint"])
    code, verifier = authorize(meta["authorization_endpoint"], client_id)
    tok = exchange(meta["token_endpoint"], client_id, code, verifier)

    access = tok.get("access_token")
    refresh = tok.get("refresh_token")
    expires_in = tok.get("expires_in")
    if not access:
        raise SystemExit(f"Token response had no access_token: {tok}")

    expires_at = ""
    if expires_in:
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat()

    update_env({
        "ROBINHOOD_CLIENT_ID": client_id,
        "ROBINHOOD_ACCESS_TOKEN": access,
        "ROBINHOOD_REFRESH_TOKEN": refresh or "",
        "ROBINHOOD_TOKEN_EXPIRES_AT": expires_at,
    })

    print(f"\n[done] tokens saved to {ENV_PATH}")
    if not refresh:
        print("WARNING: no refresh_token returned — CMA will lose access when the "
              "access token expires. Re-run this script to refresh manually.")
    else:
        print("Next: .venv/bin/python cma_lab/chunk3_robinhood_read.py")


if __name__ == "__main__":
    main()
