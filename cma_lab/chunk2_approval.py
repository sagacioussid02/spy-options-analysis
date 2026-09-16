"""
Chunk 2 — the human-approval loop (always_ask -> tool_confirmation).

This is the guardrail that becomes "approve every order" in chunk 4. Here we
rehearse it on the built-in `bash` tool so there's no money and no MCP involved
yet — but the event flow is IDENTICAL to what will gate Robinhood orders.

The flow you're learning:
    1. agent decides to use a tool whose policy is `always_ask`
    2. CMA emits  agent.tool_use  with  evaluated_permission == "ask"
    3. session goes idle with  stop_reason.type == "requires_action"   (it's
       waiting on YOU — this is exactly the case the chunk-1 gate refused to
       break on)
    4. you send  user.tool_confirmation { tool_use_id, result: allow|deny }
    5. session resumes and either runs the tool or tells the agent it was denied

Run it:
    .venv/bin/python cma_lab/chunk2_approval.py

You'll be prompted in the terminal to approve/deny the bash command. Try it both
ways — on deny, watch the agent acknowledge it couldn't run the command.
"""
from __future__ import annotations

from lab import client, console_url, get_or_create_environment, load_state, save_state

MODEL = "claude-haiku-4-5"
AGENT_STATE_KEY = "approval_agent_id"
AGENT_MODEL_KEY = "approval_agent_model"


def get_or_create_agent() -> str:
    """
    Agent whose bash tool requires approval.

    The toolset config is the key part:
      default_config.permission_policy = always_allow  -> read/glob/etc. just run
      configs[bash].permission_policy  = always_ask    -> bash pauses for you

    In chunk 4 this same shape moves onto the Robinhood MCP order tool: read-only
    market/account tools auto-run, order placement is always_ask.
    """
    state = load_state()
    agent_id = state.get(AGENT_STATE_KEY)
    if agent_id:
        if state.get(AGENT_MODEL_KEY) != MODEL:
            current = client().beta.agents.retrieve(agent_id)
            client().beta.agents.update(agent_id, version=current.version, model=MODEL)
            state[AGENT_MODEL_KEY] = MODEL
            save_state(state)
        return agent_id

    agent = client().beta.agents.create(
        name="Approval Lab Agent",
        model=MODEL,
        system=(
            "You are a lab assistant. When the user asks you to run a shell "
            "command, use the bash tool to run exactly that command, then report "
            "its output in one sentence."
        ),
        tools=[{
            "type": "agent_toolset_20260401",
            "default_config": {"enabled": True, "permission_policy": {"type": "always_allow"}},
            "configs": [
                {"name": "bash", "permission_policy": {"type": "always_ask"}},
            ],
        }],
    )
    state[AGENT_STATE_KEY] = agent.id
    state[AGENT_MODEL_KEY] = MODEL
    save_state(state)
    print(f"[chunk2] created agent {agent.id} (v{agent.version})")
    return agent.id


def ask_human(tool_use_event) -> dict:
    """
    Turn one pending tool call into a user.tool_confirmation event.

    IMPORTANT: tool_use_id is the EVENT id (sevt_...), i.e. tool_use_event.id —
    NOT a toolu_... id. This trips everyone up once.
    """
    name = getattr(tool_use_event, "name", "<tool>")
    tool_input = getattr(tool_use_event, "input", {})
    print(f"\n  >>> APPROVAL NEEDED: {name}  input={tool_input}")
    answer = input("      approve? [y/N]: ").strip().lower()

    if answer.startswith("y"):
        print("      -> ALLOW")
        return {
            "type": "user.tool_confirmation",
            "tool_use_id": tool_use_event.id,
            "result": "allow",
        }
    print("      -> DENY")
    return {
        "type": "user.tool_confirmation",
        "tool_use_id": tool_use_event.id,
        "result": "deny",
        # deny_message is surfaced to the agent so it can adjust.
        "deny_message": "Operator denied this command. Do not retry; explain instead.",
    }


def main() -> None:
    env_id = get_or_create_environment()
    agent_id = get_or_create_agent()

    session = client().beta.sessions.create(
        agent=agent_id,
        environment_id=env_id,
        title="chunk2 approval",
    )
    print(f"[chunk2] session {session.id}")
    print(f"[chunk2] watch live: {console_url(session.id)}\n")

    pending: list = []  # tool_use events awaiting our allow/deny

    with client().beta.sessions.events.stream(session_id=session.id) as stream:
        client().beta.sessions.events.send(
            session_id=session.id,
            events=[{
                "type": "user.message",
                "content": [{
                    "type": "text",
                    "text": "Use the bash tool to run:  echo 'pretend this is an order'",
                }],
            }],
        )

        for event in stream:
            print(f"  <event> {event.type}")

            if event.type == "agent.tool_use":
                # Only tools under an always_ask policy carry evaluated_permission == "ask".
                if getattr(event, "evaluated_permission", None) == "ask":
                    pending.append(event)

            elif event.type == "agent.tool_result":
                content = getattr(event, "content", None)
                print(f"    [tool ran] {content}")

            elif event.type == "agent.message":
                for block in event.content:
                    if block.type == "text":
                        print(f"    agent: {block.text}")

            elif event.type == "session.status_terminated":
                break

            elif event.type == "session.status_idle":
                stop_type = getattr(getattr(event, "stop_reason", None), "type", None)
                print(f"    [idle: stop_reason={stop_type}]")

                if stop_type == "requires_action":
                    # The agent is blocked on us. Answer every pending tool call,
                    # send the confirmations, and KEEP STREAMING (don't break) —
                    # the session resumes after it receives our decisions.
                    confirmations = [ask_human(tu) for tu in pending]
                    pending.clear()
                    client().beta.sessions.events.send(
                        session_id=session.id, events=confirmations
                    )
                    continue

                break  # end_turn / terminal -> done

    print("\n[chunk2] done. Re-run and DENY this time to see the agent adapt.")


if __name__ == "__main__":
    main()
