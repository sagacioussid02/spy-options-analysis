"""
Chunk 3, bonus — discover the FULL Robinhood MCP catalog.

Instead of guessing (or asking the agent, which can miss tools), we ask the MCP
server directly via the protocol's `tools/list` call. This prints every tool the
Robinhood Trading MCP exposes, with its description and required inputs — so you
know exactly what you can do, and which tool places orders (for chunk 4).

This talks to the MCP server straight from your machine using the access token in
cma_lab/.env (the same one CMA uses). No agent, no session, no tokens spent.

Run it:
    .venv/bin/python cma_lab/chunk3_list_tools.py

If you get a 401, your access token expired — re-run chunk3_get_robinhood_token.py.
"""
from __future__ import annotations

import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from lab import ROBINHOOD_MCP_URL, lab_env

# Heuristic: flag tools that look like they change state, so you can eyeball
# which ones MUST be gated in chunk 4.
WRITE_HINTS = ("place", "order", "buy", "sell", "cancel", "create", "submit",
               "modify", "replace", "close", "trade", "transfer", "deposit", "withdraw")


def _required(input_schema: dict) -> list[str]:
    if not isinstance(input_schema, dict):
        return []
    return list(input_schema.get("required", []) or [])


async def main() -> None:
    token = lab_env("ROBINHOOD_ACCESS_TOKEN")
    if not token:
        raise SystemExit("No ROBINHOOD_ACCESS_TOKEN in cma_lab/.env — run "
                         "chunk3_get_robinhood_token.py first.")

    headers = {"Authorization": f"Bearer {token}"}

    async with streamablehttp_client(ROBINHOOD_MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    tools = sorted(result.tools, key=lambda t: t.name)
    print(f"\nRobinhood Trading MCP exposes {len(tools)} tools:\n")

    writes = []
    for t in tools:
        is_write = any(h in t.name.lower() for h in WRITE_HINTS)
        flag = "  ⚠ WRITE" if is_write else ""
        if is_write:
            writes.append(t.name)
        req = _required(getattr(t, "inputSchema", {}) or {})
        desc = (t.description or "").strip().split("\n")[0]
        print(f"- {t.name}{flag}")
        print(f"    {desc}")
        if req:
            print(f"    required: {', '.join(req)}")
        print()

    print("=" * 60)
    if writes:
        print("State-changing tools to GATE in chunk 4 (deny unless approved):")
        for w in writes:
            print(f"  - {w}")
    else:
        print("No obviously state-changing tools matched the name heuristic — "
              "inspect the descriptions above to find the order-placement tool.")

    # Options rollout detector: agentic options trading is phased, so just check
    # whether the option-order tool has appeared for your account yet.
    names = {t.name for t in tools}
    print("\n" + "=" * 60)
    if "place_option_order" in names:
        print("OPTIONS ORDERING: ✅ AVAILABLE — place_option_order is present. "
              "Your SPY options strategy can execute through this account.")
    else:
        print("OPTIONS ORDERING: ⏳ NOT YET — no place_option_order for this "
              "account (agentic options is still rolling out). Equity only for now. "
              "Re-run this script periodically to detect when it turns on.")


if __name__ == "__main__":
    asyncio.run(main())
