"""
store_proxy — a tiny stateless HTTPS front door for the Neon "collections"
table, for callers (Claude Code cloud routines) that can reach the open
internet over HTTPS but not raw Postgres TCP.

Mirrors cma_lab/store.py's PostgresStore exactly: same table
(collections(name text primary key, data jsonb not null, updated_at
timestamptz)), same INSERT ... ON CONFLICT upsert. Auth is a bearer token, one of two kinds:
  - STORE_PROXY_TOKEN: full read+write, every collection (including
    "secrets", which holds live Robinhood tokens) reachable — treat it as
    sensitive as DATABASE_URL. Used server-side by cma_lab's HttpProxyStore.
  - STORE_PROXY_READONLY_TOKEN: GET only, PUT always 403 regardless of
    which collection. Safe to embed in a published artifact's client-side
    JS (e.g. the Desk Report page fetching journal/playbook/sleeve/events/
    usage_log directly from the browser) since a leaked copy can only ever
    read, never write fake journal entries or flip risk_overrides.

CORS is open (Access-Control-Allow-Origin: *) on GET/OPTIONS only, so a
browser page on a different origin can read with the readonly token; PUT
gets no CORS headers since it's never meant to be called from a browser.

No cross-request locking: this is a stateless function, so PostgresStore's
pg_advisory_lock (held across one load+save) doesn't translate here. Fine
for the current single-routine-at-a-time usage pattern; revisit if that
changes.

GET  /api/store?name=<collection>  -> {"data": <value>|null}
PUT  /api/store?name=<collection>  body {"data": <value>}  -> {"ok": true}
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import psycopg

_DDL = (
    "CREATE TABLE IF NOT EXISTS collections ("
    " name text PRIMARY KEY,"
    " data jsonb NOT NULL,"
    " updated_at timestamptz NOT NULL DEFAULT now())"
)


def _conn():
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    conn.execute(_DDL)
    conn.commit()
    return conn


class handler(BaseHTTPRequestHandler):
    def _write_authorized(self) -> bool:
        want = os.environ.get("STORE_PROXY_TOKEN", "")
        got = self.headers.get("Authorization", "")
        return bool(want) and got == f"Bearer {want}"

    def _read_authorized(self) -> bool:
        if self._write_authorized():
            return True
        want_ro = os.environ.get("STORE_PROXY_READONLY_TOKEN", "")
        got = self.headers.get("Authorization", "")
        return bool(want_ro) and got == f"Bearer {want_ro}"

    def _send(self, status: int, body: dict, cors: bool = False) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _name(self) -> str | None:
        qs = parse_qs(urlparse(self.path).query)
        vals = qs.get("name")
        return vals[0] if vals else None

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        if not self._read_authorized():
            self._send(401, {"error": "unauthorized"}, cors=True); return
        name = self._name()
        if not name:
            self._send(400, {"error": "missing name"}, cors=True); return
        try:
            with _conn() as conn:
                row = conn.execute(
                    "SELECT data FROM collections WHERE name = %s", (name,)
                ).fetchone()
            self._send(200, {"data": row[0] if row else None}, cors=True)
        except Exception as ex:  # noqa: BLE001
            self._send(500, {"error": str(ex)}, cors=True)

    def do_PUT(self) -> None:
        if not self._write_authorized():
            self._send(403 if self._read_authorized() else 401, {"error": "unauthorized"}); return
        name = self._name()
        if not name:
            self._send(400, {"error": "missing name"}); return
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            data = body["data"]
        except (json.JSONDecodeError, KeyError):
            self._send(400, {"error": "body must be {\"data\": ...}"}); return
        try:
            with _conn() as conn:
                conn.execute(
                    "INSERT INTO collections (name, data, updated_at)"
                    " VALUES (%s, %s::jsonb, now())"
                    " ON CONFLICT (name) DO UPDATE"
                    " SET data = EXCLUDED.data, updated_at = now()",
                    (name, json.dumps(data)),
                )
                conn.commit()
            self._send(200, {"ok": True})
        except Exception as ex:  # noqa: BLE001
            self._send(500, {"error": str(ex)})
