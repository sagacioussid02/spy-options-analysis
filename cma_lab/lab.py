"""
cma_lab/lab.py — shared helpers for the Claude Managed Agents (CMA) learning lab.

The whole point of this file is to encode the ONE rule that matters in CMA:

    Environments and Agents are PERSISTENT, versioned resources.
    You create them ONCE and reuse them by ID. Only Sessions are per-run.

So instead of calling agents.create()/environments.create() every time a script
runs (which silently piles up orphaned resources), we store their IDs in
cma_lab/cma_state.json and reuse them. That JSON file is your "I already made
these" memory across runs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import anthropic

# --- where we remember the IDs of things we've already created -----------------
STATE_PATH = Path(__file__).parent / "cma_state.json"

# CMA is in beta; the SDK sets the beta header automatically on client.beta.*,
# so we just use a normal client.
_client: Optional[anthropic.Anthropic] = None


def _dotenv() -> dict:
    """Minimal .env reader (no dependency). Parses cma_lab/.env into a dict."""
    env_file = Path(__file__).parent / ".env"
    out: dict = {}
    if not env_file.exists():
        return out
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def lab_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Read a value from cma_lab/.env first, then the OS environment."""
    import os
    return _dotenv().get(key) or os.environ.get(key) or default


# The single active ticker — one at a time. Set TICKER=<SYM> in cma_lab/.env
# (or export it) to trade/analyze something other than SPY. Every agent
# system prompt and risk_gate's symbol_whitelist read this same value, and
# decision_view.py passes it through when it launches the engine, so the
# engine and cma_lab never disagree about which ticker is active.
TICKER = lab_env("TICKER", "SPY")


def _update_env_value(key: str, value: str) -> None:
    env_file = Path(__file__).parent / ".env"
    lines = env_file.read_text().splitlines() if env_file.exists() else []
    out, seen = [], False
    for line in lines:
        if line.strip().startswith(key + "="):
            out.append(f"{key}={value}"); seen = True
        else:
            out.append(line)
    if not seen:
        out.append(f"{key}={value}")
    env_file.write_text("\n".join(out) + "\n")


def refresh_robinhood_token() -> Optional[str]:
    """Use the stored refresh_token to mint a fresh access token (public client,
    no secret) and persist it to .env. Mirrors what the CMA vault does for the
    hosted agents — but for our local-direct calls."""
    import json as _json
    import urllib.parse
    import urllib.request

    refresh = lab_env("ROBINHOOD_REFRESH_TOKEN")
    client_id = lab_env("ROBINHOOD_CLIENT_ID")
    if not (refresh and client_id):
        return None
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": client_id,
        "resource": ROBINHOOD_MCP_URL,
    }).encode()
    req = urllib.request.Request(
        ROBINHOOD_TOKEN_ENDPOINT, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req) as r:
            tok = _json.loads(r.read().decode())
    except Exception as e:  # noqa: BLE001
        print(f"[refresh] failed: {e}")
        return None
    access = tok.get("access_token")
    if not access:
        return None
    _update_env_value("ROBINHOOD_ACCESS_TOKEN", access)
    if tok.get("refresh_token"):
        _update_env_value("ROBINHOOD_REFRESH_TOKEN", tok["refresh_token"])
    print("[refresh] local Robinhood token refreshed")
    return access


def client() -> anthropic.Anthropic:
    """
    One shared Anthropic client.

    Credential precedence: cma_lab/.env (ANTHROPIC_API_KEY) first, then the
    normal SDK resolution (ANTHROPIC_API_KEY env var, etc.).
    """
    global _client
    if _client is None:
        key = _dotenv().get("ANTHROPIC_API_KEY")
        _client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
    return _client


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


def get_or_create_environment(
    name: str = "spy-cma-lab",
    state_key: str = "environment_id",
) -> str:
    """
    Return an environment_id, creating the environment only the first time.

    An environment is just a template for the sandbox container your agent's
    tools run in. 'cloud' = Anthropic hosts it; 'unrestricted' networking = the
    container has full outbound internet (we'll tighten this later for safety).
    """
    state = load_state()
    env_id = state.get(state_key)

    if env_id:
        # Confirm it still exists; if it was deleted out from under us, recreate.
        try:
            client().beta.environments.retrieve(env_id)
            return env_id
        except anthropic.NotFoundError:
            pass

    env = client().beta.environments.create(
        name=name,
        config={"type": "cloud", "networking": {"type": "unrestricted"}},
    )
    state[state_key] = env.id
    save_state(state)
    print(f"[lab] created environment {env.id}")
    return env.id


def console_url(session_id: str, workspace: str = "default") -> str:
    """A clickable link to watch the session live in the Anthropic Console."""
    return f"https://platform.claude.com/workspaces/{workspace}/sessions/{session_id}"


# USD per 1M tokens: (input, output). Cache reads ~0.1x input, writes ~1.25x.
MODEL_PRICES = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
}


def report_cost(session_id: str, model: str = "claude-haiku-4-5") -> float:
    """Print this session's token usage and an estimated USD cost. Returns the
    estimate. Reads usage off the session object after it goes idle."""
    try:
        s = client().beta.sessions.retrieve(session_id)
        usage = getattr(s, "usage", None)
        u = usage.to_dict() if hasattr(usage, "to_dict") else (dict(usage) if usage else {})
    except Exception as e:  # noqa: BLE001
        print(f"[cost] could not fetch usage: {e}")
        return 0.0

    fresh_in = u.get("input_tokens") or 0
    out = u.get("output_tokens") or 0
    cache_read = u.get("cache_read_input_tokens") or 0
    cache_write = u.get("cache_creation_input_tokens") or 0
    in_rate, out_rate = MODEL_PRICES.get(model, (1.0, 5.0))

    cost = (
        fresh_in / 1e6 * in_rate
        + cache_read / 1e6 * in_rate * 0.1
        + cache_write / 1e6 * in_rate * 1.25
        + out / 1e6 * out_rate
    )
    print(f"[cost] {model}: input {fresh_in} fresh + {cache_read} cached + "
          f"{cache_write} written, output {out}")
    print(f"[cost] estimated this run: ${cost:.4f}")
    return cost


# ============================== Robinhood / vaults ============================
# Values discovered from Robinhood's published OAuth metadata:
#   https://agent.robinhood.com/.well-known/oauth-authorization-server
ROBINHOOD_MCP_URL = "https://agent.robinhood.com/mcp/trading"
ROBINHOOD_TOKEN_ENDPOINT = "https://api.robinhood.com/oauth2/token/"
ROBINHOOD_SCOPE = "internal"


def get_or_create_vault(
    display_name: str = "spy-robinhood-vault",
    state_key: str = "vault_id",
) -> str:
    """
    A vault holds MCP credentials that Anthropic manages + auto-refreshes.

    Crucial security property: the credential NEVER enters the agent's container.
    CMA injects it by proxy *after* a tool call leaves the sandbox, so even a
    prompt-injected agent cannot read or exfiltrate your Robinhood token.
    """
    state = load_state()
    vid = state.get(state_key)
    if vid:
        try:
            client().beta.vaults.retrieve(vid)
            return vid
        except anthropic.NotFoundError:
            pass
    vault = client().beta.vaults.create(display_name=display_name)
    state[state_key] = vault.id
    save_state(state)
    print(f"[lab] created vault {vault.id}")
    return vault.id


def ensure_robinhood_credential(vault_id: str, force: bool = False) -> None:
    """
    Store the Robinhood OAuth tokens (captured by chunk3_get_robinhood_token.py
    into cma_lab/.env) as an mcp_oauth credential inside the vault. Idempotent:
    only created once unless force=True.

    The `refresh` block is what lets CMA keep the session alive indefinitely —
    it posts the refresh_token to Robinhood's token endpoint when the access
    token nears expiry. token_endpoint_auth is {"type": "none"} because
    Robinhood registers public OAuth clients (no client secret).
    """
    state = load_state()
    if state.get("robinhood_credential_id") and not force:
        return

    access = lab_env("ROBINHOOD_ACCESS_TOKEN")
    refresh = lab_env("ROBINHOOD_REFRESH_TOKEN")
    client_id = lab_env("ROBINHOOD_CLIENT_ID")
    expires_at = lab_env("ROBINHOOD_TOKEN_EXPIRES_AT")

    if not (access and client_id):
        raise SystemExit(
            "Missing Robinhood tokens in cma_lab/.env.\n"
            "Run:  .venv/bin/python cma_lab/chunk3_get_robinhood_token.py  first."
        )

    auth: dict = {
        "type": "mcp_oauth",
        "mcp_server_url": ROBINHOOD_MCP_URL,
        "access_token": access,
    }
    if expires_at:
        auth["expires_at"] = expires_at
    if refresh:
        auth["refresh"] = {
            "client_id": client_id,
            "refresh_token": refresh,
            "token_endpoint": ROBINHOOD_TOKEN_ENDPOINT,
            "token_endpoint_auth": {"type": "none"},
            "resource": ROBINHOOD_MCP_URL,
            "scope": ROBINHOOD_SCOPE,
        }

    cred = client().beta.vaults.credentials.create(
        vault_id, auth=auth, display_name="Robinhood Trading MCP"
    )
    state["robinhood_credential_id"] = cred.id
    save_state(state)
    print(f"[lab] stored Robinhood credential {cred.id} in vault {vault_id}")


# ====================== deterministic MCP tool calls =========================
# These let YOUR code call Robinhood tools directly (host-side), with no LLM in
# the loop — used for executing an order the human already approved.
async def _mcp_call(name: str, arguments: dict) -> str:
    import importlib
    ClientSession = importlib.import_module("mcp").ClientSession
    streamablehttp_client = importlib.import_module(
        "mcp.client.streamable_http").streamablehttp_client

    token = lab_env("ROBINHOOD_ACCESS_TOKEN")
    headers = {"Authorization": f"Bearer {token}"}
    async with streamablehttp_client(ROBINHOOD_MCP_URL, headers=headers) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            parts = []
            for block in getattr(result, "content", []) or []:
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)
            return "\n".join(parts)


def _is_auth_error(exc) -> bool:
    """Detect a 401 even when wrapped in an anyio ExceptionGroup / chained."""
    s = str(exc)
    if "401" in s or "Unauthorized" in s:
        return True
    for sub in (getattr(exc, "exceptions", None) or []):
        if _is_auth_error(sub):
            return True
    for chained in (getattr(exc, "__cause__", None), getattr(exc, "__context__", None)):
        if chained is not None and _is_auth_error(chained):
            return True
    return False


def mcp_call_tool(name: str, arguments: dict) -> str:
    """Synchronous Robinhood MCP tool call. Returns the tool's text output.
    On a 401 (expired token), refreshes the local token once and retries."""
    import asyncio
    try:
        return asyncio.run(_mcp_call(name, arguments))
    except BaseException as e:  # noqa: BLE001  (ExceptionGroup is BaseException)
        if _is_auth_error(e) and refresh_robinhood_token():
            return asyncio.run(_mcp_call(name, arguments))
        raise


def account_standing(account: Optional[str] = None) -> dict:
    """Live account standing from Robinhood get_portfolio. buying_power is the
    authoritative spendable figure — what the user can actually afford."""
    import json as _json
    account = account or lab_env("ROBINHOOD_ACCOUNT_NUMBER")
    data = _json.loads(mcp_call_tool("get_portfolio", {"account_number": account})).get("data", {})
    bp = data.get("buying_power", {}) or {}
    return {
        "buying_power": float(bp.get("buying_power") or data.get("cash") or 0),
        "cash": float(data.get("cash") or 0),
        "total_value": float(data.get("total_value") or 0),
        "equity_value": float(data.get("equity_value") or 0),
        "currency": data.get("currency", "USD"),
    }


# ============================== session driver ===============================
def drive_session_with_approval(
    session_id: str,
    *,
    kickoff_text: str,
    approve_fn,
    verbose: bool = True,
) -> None:
    """
    Reusable version of the chunk-2 loop. Streams a session, sends the kickoff
    message, and whenever a tool under an `always_ask` policy wants to run,
    calls approve_fn(name, tool_input) -> (allow: bool, deny_message: str|None)
    and replies with user.tool_confirmation.

    Handles BOTH built-in tools (agent.tool_use) and MCP tools
    (agent.mcp_tool_use) — that's why chunk 3 (MCP) can reuse it unchanged.
    """
    c = client()
    pending: list = []

    with c.beta.sessions.events.stream(session_id=session_id) as stream:
        c.beta.sessions.events.send(
            session_id=session_id,
            events=[{"type": "user.message",
                     "content": [{"type": "text", "text": kickoff_text}]}],
        )
        for event in stream:
            if verbose:
                print(f"  <event> {event.type}")

            if event.type in ("agent.tool_use", "agent.mcp_tool_use"):
                if getattr(event, "evaluated_permission", None) == "ask":
                    pending.append(event)
                elif verbose:
                    print(f"    [auto-ran] {getattr(event, 'name', '?')} "
                          f"{getattr(event, 'input', {})}")

            elif event.type in ("agent.tool_result", "agent.mcp_tool_result"):
                if verbose:
                    print(f"    [result] {str(getattr(event, 'content', ''))[:400]}")

            elif event.type == "agent.message":
                for block in event.content:
                    if block.type == "text":
                        print(f"    agent: {block.text}")

            elif event.type == "session.error":
                print(f"    [SESSION ERROR] {getattr(event, 'error', event)}")

            elif event.type == "session.status_terminated":
                break

            elif event.type == "session.status_idle":
                stop_type = getattr(getattr(event, "stop_reason", None), "type", None)
                if verbose:
                    print(f"    [idle: stop_reason={stop_type}]")
                if stop_type == "requires_action":
                    confs = []
                    for tu in pending:
                        allow, deny_msg = approve_fn(
                            getattr(tu, "name", "<tool>"),
                            getattr(tu, "input", {}),
                        )
                        conf = {
                            "type": "user.tool_confirmation",
                            "tool_use_id": tu.id,
                            "result": "allow" if allow else "deny",
                        }
                        if not allow and deny_msg:
                            conf["deny_message"] = deny_msg
                        confs.append(conf)
                    pending.clear()
                    # CMA can re-emit a requires_action idle for tools we already
                    # answered (a transient race). Only send if we actually have
                    # new confirmations — an empty events list is a 400.
                    if confs:
                        c.beta.sessions.events.send(session_id=session_id, events=confs)
                    continue
                break
