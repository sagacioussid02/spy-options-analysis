"""
Chunk 1 — CMA "hello world".

Goal: feel the full create-once -> session-per-run -> stream-events loop with a
trivial task and NO Robinhood, NO money, NO custom tools. Just the skeleton.

Run it:
    .venv/bin/python cma_lab/chunk1_hello.py

Run it a SECOND time and watch: it reuses the same environment + agent IDs from
cma_state.json and only creates a new session. That's the pattern you'll keep.

What to watch in the output:
  - the stream prints every event TYPE as it arrives — that's the agent loop
    narrating itself (model requests, tool use, messages, status changes).
  - we open the stream BEFORE sending the message ("stream-first") so we don't
    miss the early events.
  - we stop on a *terminal* idle, not just any idle (see the gate below).
"""
from __future__ import annotations

from lab import client, console_url, get_or_create_environment, load_state, save_state

# The model lives on the AGENT, not the session. Haiku is the cheapest 4.x model
# ($1/$5 per 1M tokens) and is plenty for this lab. Bump to "claude-sonnet-4-6"
# or "claude-opus-4-8" later for the judgment-heavy trading agent if you want.
MODEL = "claude-haiku-4-5"
AGENT_STATE_KEY = "hello_agent_id"
AGENT_MODEL_KEY = "hello_agent_model"  # remember which model the saved agent uses


def get_or_create_agent() -> str:
    """
    Create the agent once; reuse its ID on every later run.

    Subtlety: because we cache the agent ID, editing MODEL above does NOT change
    an agent you already created. So if the saved model differs from MODEL, we
    push a new agent VERSION via agents.update() — that's how CMA config evolves
    (every update is a new immutable version; running sessions keep their old one,
    new sessions get the latest). We pass the current version as an optimistic
    lock so a concurrent edit can't silently clobber ours.
    """
    state = load_state()
    agent_id = state.get(AGENT_STATE_KEY)

    if agent_id:
        if state.get(AGENT_MODEL_KEY) != MODEL:
            current = client().beta.agents.retrieve(agent_id)
            updated = client().beta.agents.update(
                agent_id, version=current.version, model=MODEL
            )
            state[AGENT_MODEL_KEY] = MODEL
            save_state(state)
            print(f"[chunk1] updated agent {agent_id} -> {MODEL} (v{updated.version})")
        return agent_id

    agent = client().beta.agents.create(
        name="Hello Agent",
        model=MODEL,
        system="You are a concise assistant. Answer in one short sentence.",
        # The prebuilt toolset (bash, read, write, edit, glob, grep, web_*).
        # We enable it so the agent *has* a container to act in, even though
        # this trivial task won't need it.
        tools=[{"type": "agent_toolset_20260401"}],
    )
    state[AGENT_STATE_KEY] = agent.id
    state[AGENT_MODEL_KEY] = MODEL
    save_state(state)
    print(f"[chunk1] created agent {agent.id} (v{agent.version})")
    return agent.id


def drain(session_id: str) -> None:
    """
    Open the event stream and print everything until the session is DONE.

    The break gate is the subtle part of CMA:
      - session.status_terminated  -> always stop.
      - session.status_idle        -> stop ONLY if its stop_reason is terminal.
        An idle with stop_reason 'requires_action' means the agent is waiting on
        US (a tool confirmation / custom tool result) and would deadlock if we
        broke here. We don't hit that in chunk 1, but we code the gate correctly
        now so chunks 2+ just work.
    """
    with client().beta.sessions.events.stream(session_id=session_id) as stream:
        for event in stream:
            print(f"  <event> {event.type}")

            if event.type == "agent.message":
                for block in event.content:
                    if block.type == "text":
                        print(f"    agent: {block.text}")

            elif event.type == "session.status_terminated":
                print("  [session terminated]")
                break

            elif event.type == "session.status_idle":
                stop = getattr(event, "stop_reason", None)
                stop_type = getattr(stop, "type", None)
                print(f"    [idle: stop_reason={stop_type}]")
                if stop_type != "requires_action":
                    break  # end_turn / retries_exhausted -> terminal, we're done


def main() -> None:
    env_id = get_or_create_environment()
    agent_id = get_or_create_agent()

    # The ONE per-run object. Points at agent + environment; carries no config.
    session = client().beta.sessions.create(
        agent=agent_id,                 # string shorthand = latest agent version
        environment_id=env_id,
        title="chunk1 hello",
    )
    print(f"[chunk1] session {session.id}")
    print(f"[chunk1] watch live: {console_url(session.id)}\n")

    # Stream-FIRST, then send — so we capture the early events.
    with client().beta.sessions.events.stream(session_id=session.id) as stream:
        client().beta.sessions.events.send(
            session_id=session.id,
            events=[{
                "type": "user.message",
                "content": [{"type": "text", "text": "Say hello and tell me what 17 * 23 is."}],
            }],
        )
        for event in stream:
            print(f"  <event> {event.type}")
            if event.type == "agent.message":
                for block in event.content:
                    if block.type == "text":
                        print(f"    agent: {block.text}")
            elif event.type == "session.status_terminated":
                break
            elif event.type == "session.status_idle":
                stop_type = getattr(getattr(event, "stop_reason", None), "type", None)
                print(f"    [idle: stop_reason={stop_type}]")
                if stop_type != "requires_action":
                    break

    print("\n[chunk1] done. Run again — it'll reuse the same agent/env, new session.")


if __name__ == "__main__":
    main()
