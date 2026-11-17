"""Sutra adapter: the SPY desk's read tools as a local HTTP API plus an Agent Manifest.

Sutra's gateway reaches a project through ``GET /.well-known/sutra-agent.json``
and flat HTTP tools (GET with query args, POST with a JSON body) under a 15
second timeout. This adapter wraps the same functions as ``mcp_server.py``
(the stdio server, unchanged) and:

- binds to 127.0.0.1 only and refuses any Host header that isn't local, so a
  browser can't reach it through DNS rebinding;
- requires ``X-Spy-Desk-Token`` (``SPY_DESK_TOKEN``) on every tool call, and
  refuses to start without it. The manifest and ``/api/health`` stay open:
  Sutra fetches the manifest without credentials and the watcher only reads
  health;
- lists only read tools plus two analysis tools that return an id at once and
  finish in the background (the engine run can take 15 minutes);
- never lists ``execute_confirmed_trade`` or ``run_paper_sweep``, and blocks
  every broker call except a fixed set of reads for the whole process (see
  :func:`install_broker_guard`), so nothing reached through this adapter can
  place, cancel or review an order;
- never sets or changes ``SPY_LIVE``. ``/api/health`` reports whether live
  trading is armed, and that is all.

Run from ``cma_lab/`` (or use the launchd plist in ``launchd/``)::

    ../.venv/bin/python sutra_api.py
"""
from __future__ import annotations

import hmac
import os
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import mcp_server

PROJECT_NAME = "spy-desk"
DEFAULT_PORT = 8790
TOKEN_HEADER = "X-Spy-Desk-Token"
MAX_RUNS = 50
# A broker token that runs out within this window, with no way to refresh it,
# makes the desk report degraded.
TOKEN_WARN_SECONDS = 24 * 3600

# The only Robinhood MCP tools any code in this process may call. Everything
# else (place_equity_order, review_equity_order, cancel..., watchlist writes)
# raises BrokerWriteBlocked before a request leaves the machine.
BROKER_READ_TOOLS = frozenset({
    "get_portfolio",
    "get_equity_positions",
    "get_equity_orders",
    "get_equity_quotes",
})


class ToolError(Exception):
    """A bad request from the caller: reported as a 400."""


class BrokerWriteBlocked(RuntimeError):
    """A broker call outside BROKER_READ_TOOLS was attempted in the adapter."""


def install_broker_guard() -> None:
    """Allow only BROKER_READ_TOOLS through ``lab._mcp_call`` for this process.

    Every Robinhood call in cma_lab goes through ``lab.mcp_call_tool``, which
    looks up ``_mcp_call`` on the ``lab`` module at call time, including its
    retry after a token refresh. Wrapping it here therefore covers callers that
    imported ``mcp_call_tool`` by name too (``execution``, ``sweep``).
    """
    import lab

    current = lab._mcp_call
    if getattr(current, "_sutra_read_only", False):
        return

    async def guarded(name: str, arguments: dict) -> str:
        if name not in BROKER_READ_TOOLS:
            raise BrokerWriteBlocked(f"broker tool {name!r} is not allowed through the Sutra adapter")
        return await current(name, arguments)

    guarded._sutra_read_only = True  # type: ignore[attr-defined]
    lab._mcp_call = guarded


# --------------------------------------------------------------------------- tools


@dataclass(frozen=True)
class Arg:
    name: str
    type: str = "string"  # string | number
    required: bool = False


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    tier_hint: str  # read-only | confirm-first
    method: str  # GET | POST
    fn: Callable[..., Any]
    args: tuple[Arg, ...] = ()

    @property
    def path(self) -> str:
        return f"/api/{self.name}"


class Runs:
    """Engine runs in the background, one at a time, kept in memory."""

    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="spy-sutra-engine")
        self._runs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def submit(self, ticker: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        run_id = "run_" + uuid.uuid4().hex[:12]
        record = {"run_id": run_id, "ticker": ticker, "status": "running",
                  "started_at": _now()}
        with self._lock:
            self._runs[run_id] = record
            while len(self._runs) > MAX_RUNS:
                self._runs.popitem(last=False)

        def work() -> None:
            try:
                report = fn()
                if isinstance(report, dict) and report.get("error"):
                    update = {"status": "failed", "error": report["error"]}
                else:
                    update = {"status": "done", "report": report}
            except Exception as exc:  # noqa: BLE001  report the type, not a trace
                update = {"status": "failed", "error": f"{type(exc).__name__} (see the adapter log)"}
            with self._lock:
                if run_id in self._runs:
                    self._runs[run_id].update(update, finished_at=_now())

        self._pool.submit(work)
        return dict(record)

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            return dict(run) if run else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _start_engine_run(runs: Runs, ticker: str) -> dict[str, Any]:
    from risk_gate import load_risk_config

    symbol = str(ticker).strip().upper()
    allowed = {item.upper() for item in load_risk_config().symbol_whitelist}
    if symbol not in allowed:
        return {"error": f"Ticker {symbol!r} is not in the configured whitelist.",
                "allowed_symbols": sorted(allowed)}
    record = runs.submit(symbol, lambda: mcp_server.run_engine(symbol))
    record["message"] = "The engine runs in the background. Poll get_engine_run with this run_id."
    return record


def _get_engine_run(runs: Runs, run_id: str) -> dict[str, Any]:
    run = runs.get(run_id)
    if run is None:
        return {"error": "Unknown run_id. Runs are kept in memory, so a restart forgets them."}
    return run


def _analyze_trade_request(ticker: str, side: str, quantity: float,
                           entry_style: str = "market",
                           limit_price: float | None = None) -> dict[str, Any]:
    review = mcp_server.analyze_trade_request(
        ticker, side, quantity, entry_style, limit_price, wait_seconds=0)
    if isinstance(review, dict) and review.get("status") == "running":
        review = dict(review)
        review["message"] = ("Analysis runs in the background. Poll get_trade_analysis_details "
                             "with this review_id. No order is placed from here.")
    return review


class _Desk:
    """Looks up each mcp_server function when it is called, not when the app is built."""

    def __getattr__(self, name: str) -> Callable[..., Any]:
        def call(**kwargs: Any) -> Any:
            return getattr(mcp_server, name)(**kwargs)

        call.__name__ = name
        return call


def _tools(runs: Runs) -> tuple[Tool, ...]:
    m = _Desk()
    limit = Arg("limit", "number")
    ticker = Arg("ticker", required=True)
    return (
        Tool("get_engine_signal", "Read the latest engine decision report. Does not refresh analysis or place orders.", "read-only", "GET", m.get_engine_signal),
        Tool("get_recent_debates", "Read recent committee debates, including Bull/Bear cases and the PM outcome.", "read-only", "GET", m.get_recent_debates, (limit,)),
        Tool("get_journal_summary", "Read the desk journal's performance summary. No writes or broker calls.", "read-only", "GET", m.get_journal_summary),
        Tool("get_recent_trades", "Read recent journal entries, including proposals and execution status.", "read-only", "GET", m.get_recent_trades, (limit,)),
        Tool("get_open_positions", "Read open positions from the desk journal (not a broker reconciliation).", "read-only", "GET", m.get_open_positions),
        Tool("get_unreconciled_orders", "Read journal orders awaiting broker reconciliation. Does not contact the broker.", "read-only", "GET", m.get_unreconciled_orders),
        Tool("get_broker_account", "Read Robinhood balances and buying power. Read-only.", "read-only", "GET", m.get_broker_account),
        Tool("get_broker_positions", "Read current Robinhood equity positions. Read-only.", "read-only", "GET", m.get_broker_positions),
        Tool("get_broker_orders", "Read Robinhood equity order history. Never places or changes orders.", "read-only", "GET", m.get_broker_orders, (Arg("order_id"),)),
        Tool("get_ticker_trade_status", "Broker shares, broker orders and journal entries for one whitelisted ticker. Read-only.", "read-only", "GET", m.get_ticker_trade_status, (ticker,)),
        Tool("get_risk_settings", "Read the hard limits, ticker whitelist and kill-switch state.", "read-only", "GET", m.get_risk_settings),
        Tool("get_lessons", "Read the desk's current distilled lessons.", "read-only", "GET", m.get_lessons),
        Tool("get_trade_analysis_details", "Read a cached trade analysis by review_id, with backtest and sentiment details.", "read-only", "GET", m.get_trade_analysis_details, (Arg("review_id", required=True),)),
        Tool("get_trading_analyst_status", "Summary of a ticker's latest cached trade review and its broker/journal status. Read-only.", "read-only", "GET", m.get_trading_analyst_status, (ticker,)),
        Tool("preview_sweep", "Preview mechanical stop/target/time-stop exits. Reads quotes only and changes nothing.", "read-only", "GET", m.preview_sweep),
        Tool("get_engine_run", "Status of a background engine run started by run_engine, with its report when done.", "read-only", "GET", lambda run_id: _get_engine_run(runs, run_id), (Arg("run_id", required=True),)),
        Tool("run_engine", "Refresh one whitelisted ticker's engine report in the background and return a run_id at once. Analysis only; cannot place orders.", "confirm-first", "POST", lambda ticker: _start_engine_run(runs, ticker), (ticker,)),
        Tool("analyze_trade_request", "Start a pre-trade analysis (fresh engine run plus a three-year backtest) and return a review_id at once. Never places an order.", "confirm-first", "POST", _analyze_trade_request,
             (ticker, Arg("side", required=True), Arg("quantity", "number", required=True), Arg("entry_style"), Arg("limit_price", "number"))),
    )  # fmt: skip


# Tools that must never appear in this adapter, whatever else changes.
NEVER_LISTED = frozenset({"execute_confirmed_trade", "run_paper_sweep",
                          "create_trade_proposal", "reject_trade_proposal",
                          "wait_for_trade_analysis"})


def manifest(tools: tuple[Tool, ...]) -> dict[str, Any]:
    """The Sutra Agent Manifest (v1), generated from the tool table so it cannot drift."""
    return {
        "sutra_manifest_version": 1,
        "project": {
            "name": PROJECT_NAME,
            "description": "SPY options desk: engine signals, journal, broker reads and pre-trade "
                           "analysis. Read and analyze only; no order can be placed through Sutra.",
        },
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "tier_hint": t.tier_hint,
                "method": t.method,
                "path": t.path,
                "args": [
                    {"name": a.name, "type": a.type, "required": a.required, "secret": False,
                     "in": "query" if t.method == "GET" else "body"}
                    for a in t.args
                ],
                "generic_callable": True,
            }
            for t in tools
        ],
    }


def _coerce(arg: Arg, raw: Any) -> Any:
    if arg.type == "number":
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            raise ToolError(f"argument {arg.name!r} must be a number")
        try:
            value = float(raw)
        except ValueError as exc:
            raise ToolError(f"argument {arg.name!r} must be a number") from exc
        return int(value) if arg.name == "limit" else value
    if not isinstance(raw, str):
        raise ToolError(f"argument {arg.name!r} must be a string")
    return raw


def _bind(tool: Tool, supplied: dict[str, Any]) -> dict[str, Any]:
    known = {a.name for a in tool.args}
    unknown = set(supplied) - known
    if unknown:
        raise ToolError(f"unknown argument(s): {sorted(unknown)}")
    out: dict[str, Any] = {}
    for a in tool.args:
        if a.name in supplied and supplied[a.name] not in (None, ""):
            out[a.name] = _coerce(a, supplied[a.name])
        elif a.required:
            raise ToolError(f"missing required argument {a.name!r}")
    return out


# -------------------------------------------------------------------------- health


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes")


def health() -> dict[str, Any]:
    """Desk health for sutra-watch. Reports state only; holds no tokens or balances."""
    from lab import lab_env

    problems: list[str] = []
    broker: dict[str, Any] = {}
    try:
        token_present = bool(lab_env("ROBINHOOD_ACCESS_TOKEN"))
        refresh_available = bool(lab_env("ROBINHOOD_REFRESH_TOKEN") and lab_env("ROBINHOOD_CLIENT_ID"))
        expires_raw = lab_env("ROBINHOOD_TOKEN_EXPIRES_AT")
        live_armed = _truthy(lab_env("SPY_LIVE")) and not _truthy(lab_env("SPY_SIM_ONLY"))
    except Exception as exc:  # noqa: BLE001  e.g. the secrets store is unreachable
        return {"status": "degraded", "problems": [f"settings unreadable ({type(exc).__name__})"],
                "checked_at": _now()}

    expires_at = None
    seconds_left = None
    if expires_raw:
        try:
            expires_at = datetime.fromisoformat(expires_raw)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            seconds_left = (expires_at - datetime.now(timezone.utc)).total_seconds()
        except ValueError:
            problems.append("broker token expiry unreadable")
    broker = {
        "token_present": token_present,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "refresh_available": refresh_available,
    }
    if not token_present:
        problems.append("broker token missing")
    elif seconds_left is not None and not refresh_available:
        if seconds_left <= 0:
            problems.append("broker token expired and cannot refresh")
        elif seconds_left < TOKEN_WARN_SECONDS:
            problems.append("broker token expires within a day and cannot refresh")

    report_age_hours = None
    try:
        mtime = mcp_server.DECISION_PATH.stat().st_mtime
        report_age_hours = round((time.time() - mtime) / 3600, 1)
    except OSError:
        pass

    return {
        "status": "degraded" if problems else "ok",
        "problems": problems,
        "broker": broker,
        "engine": {"last_report_age_hours": report_age_hours},
        "live_trading_armed": live_armed,
        "checked_at": _now(),
    }


# ----------------------------------------------------------------------------- app


def build_app(token: str, *, port: int = DEFAULT_PORT, runs: Runs | None = None,
              guard_broker: bool = True) -> FastAPI:
    if not token:
        raise ValueError("SPY_DESK_TOKEN is required")
    if guard_broker:
        install_broker_guard()
    run_table = runs or Runs()
    tools = _tools(run_table)
    assert not NEVER_LISTED & {t.name for t in tools}, "a write tool slipped into the manifest"

    app = FastAPI(title="spy desk sutra adapter", docs_url=None, redoc_url=None, openapi_url=None)
    allowed_hosts = {f"{h}:{port}" for h in ("127.0.0.1", "localhost", "[::1]")}
    open_paths = {"/.well-known/sutra-agent.json", "/api/health"}

    @app.middleware("http")
    async def _guard(request: Request, call_next: Callable[[Request], Any]) -> Any:
        if request.headers.get("host", "").lower() not in allowed_hosts:
            return JSONResponse({"error": "forbidden host"}, status_code=403)
        if request.url.path not in open_paths:
            supplied = request.headers.get(TOKEN_HEADER, "")
            if not hmac.compare_digest(supplied.encode(), token.encode()):
                return JSONResponse({"error": "missing or invalid token"}, status_code=401)
            if request.method == "POST" and not request.headers.get(
                    "content-type", "").lower().startswith("application/json"):
                return JSONResponse({"error": "content-type must be application/json"}, status_code=415)
        return await call_next(request)

    @app.get("/.well-known/sutra-agent.json")
    def _manifest() -> dict[str, Any]:
        return manifest(tools)

    @app.get("/api/health")
    def _health() -> JSONResponse:
        return JSONResponse(health())

    def register(tool: Tool) -> None:
        async def endpoint(request: Request) -> JSONResponse:
            try:
                if tool.method == "GET":
                    supplied: dict[str, Any] = dict(request.query_params)
                else:
                    body = await request.json() if await request.body() else {}
                    if not isinstance(body, dict):
                        raise ToolError("body must be a JSON object")
                    supplied = body
                kwargs = _bind(tool, supplied)
                # Tool functions do blocking I/O; run them off the event loop.
                from starlette.concurrency import run_in_threadpool

                result = await run_in_threadpool(tool.fn, **kwargs)
                return JSONResponse({"result": result})
            except ToolError as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)
            except ValueError:
                return JSONResponse({"error": "invalid JSON body"}, status_code=400)
            except BrokerWriteBlocked as exc:
                return JSONResponse({"error": str(exc)}, status_code=403)
            except Exception as exc:  # noqa: BLE001
                return JSONResponse({"error": f"{type(exc).__name__} (see the adapter log)"},
                                    status_code=500)

        app.add_api_route(tool.path, endpoint, methods=[tool.method], name=tool.name)

    for t in tools:
        register(t)
    return app


def main() -> None:
    import uvicorn
    from lab import lab_env

    token = lab_env("SPY_DESK_TOKEN")
    if not token:
        raise SystemExit("SPY_DESK_TOKEN is not set; refusing to start the Sutra adapter.")
    port = int(os.environ.get("SPY_DESK_SUTRA_PORT", DEFAULT_PORT))
    uvicorn.run(build_app(token, port=port), host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
