"""
Inspect your CMA agents and sessions — the "is it running / show me logs" tool.

    .venv/bin/python cma_lab/logs.py            # list agents + recent sessions
    .venv/bin/python cma_lab/logs.py <session>  # dump one session's event log

Remember: agents are persisted configs, not daemons. "running" only ever shows on
a SESSION, and only while it's actively working. Idle/terminated = nothing
running = no cost.
"""
from __future__ import annotations

import sys

from lab import client, console_url, load_state


def list_agents() -> None:
    print("AGENTS (hosted configs — these don't 'run', they're invoked per session):")
    state = load_state()
    known = {v: k for k, v in state.items() if k.endswith("agent_id")}
    n = 0
    for a in client().beta.agents.list():
        label = known.get(a.id, "")
        print(f"  {a.id}  v{a.version:<4}  {a.name}  {('<- ' + label) if label else ''}")
        n += 1
        if n >= 25:
            break
    if n == 0:
        print("  (none)")


def list_sessions(limit: int = 15) -> None:
    print(f"\nRECENT SESSIONS (status is the real 'running' indicator):")
    n = 0
    for s in client().beta.sessions.list():
        print(f"  {s.id}  [{s.status:<11}]  {getattr(s, 'title', '') or ''}  "
              f"{getattr(s, 'created_at', '')}")
        n += 1
        if n >= limit:
            break
    if n == 0:
        print("  (none yet)")
    print("\nWatch any session live in the Console:")
    print("  https://platform.claude.com/workspaces/default/sessions")


def dump_events(session_id: str) -> None:
    print(f"EVENT LOG for {session_id}")
    print(f"Console: {console_url(session_id)}\n")
    events = client().beta.sessions.events.list(session_id=session_id)
    for e in events.data:
        line = f"  {getattr(e, 'processed_at', '') or '':<28} {e.type}"
        # surface the useful payloads
        if e.type == "agent.message":
            for b in getattr(e, "content", []) or []:
                if getattr(b, "type", None) == "text":
                    line += f"  | {b.text[:120]}"
        elif e.type in ("agent.mcp_tool_use", "agent.custom_tool_use", "agent.tool_use"):
            line += f"  | {getattr(e, 'name', '')} {str(getattr(e, 'input', ''))[:80]}"
        print(line)


def main() -> None:
    if len(sys.argv) > 1:
        dump_events(sys.argv[1])
    else:
        list_agents()
        list_sessions()


if __name__ == "__main__":
    main()
