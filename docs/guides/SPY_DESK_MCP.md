# SPY Desk MCP Server

`cma_lab/mcp_server.py` exposes this project's desk capabilities to Sutra using
local MCP stdio transport. The server runs as a child process and does not open
a network listener.

## Connect From Sutra

Add this to Sutra's MCP configuration, replacing the paths with the actual
workspace paths:

```json
{
  "mcpServers": {
    "spy-desk": {
      "command": "/absolute/path/to/spy/.venv/bin/python",
      "args": ["/absolute/path/to/spy/cma_lab/mcp_server.py"]
    }
  }
}
```

Do not put credentials in Sutra's MCP configuration or expose this writable
local process to untrusted clients.

## Read-Only Tools

- `get_engine_signal`: latest general engine report. For a fresh per-ticker result, use analyst review.
- `get_recent_debates`: recent Bull/Bear cases and PM outcomes.
- `get_journal_summary`, `get_recent_trades`: project journal and performance.
- `get_open_positions`, `get_unreconciled_orders`: local journal state, not broker reconciliation.
- `get_broker_account`, `get_broker_positions`, `get_broker_orders`: Robinhood read-only broker data.
- `get_ticker_trade_status(ticker)`: broker positions/orders plus matching local journal state.
- `get_risk_settings`, `get_lessons`: active limits and distilled lessons.
- `preview_sweep`: report mechanical exits without changing state.
- `get_trade_analysis_details(review_id)`: full cached analyst report.
- `get_trading_analyst_status(ticker)`: concise latest cached review and execution state.

## Analyst Workflow

1. Call `analyze_trade_request(ticker, side, quantity, entry_style, limit_price)`.
   It validates the request against the active ticker whitelist, quantity and
   risk limits, runs fresh isolated engine analysis plus a three-year daily-bar
   replay of the existing strategy library, and caches the result under a
   `review_id`. Sentiment comes from the same fresh engine run.
2. The response gives a concise `confident` or `doubt` judgment and its reasons.
   Call `get_trade_analysis_details(review_id)` for full momentum, sentiment,
   backtest, and judgment evidence.
3. The first wait is capped at 120 seconds. If still running, the response
   includes a `review_id` and tells Sutra to ask whether the user wants to wait
   with `wait_for_trade_analysis` or proceed without results.
4. After presenting the analysis, wait for the user's separate confirmation
   before calling `execute_confirmed_trade(review_id, confirm=true)`. If the
   analyst reported doubts, require the user to acknowledge them with
   `acknowledge_doubts=true`.

A running/failed analysis is blocked unless the user explicitly chooses
`proceed_without_analysis=true` along with `confirm=true`. That bypass is visible
in the cached review and still goes through live risk and price preflight.
Completed analysis is cached in the `trade_reviews` collection. An identical
request within 15 minutes reuses that cached review; a new request after that
runs fresh analysis. Engine output is written to a private per-review temporary
reports directory so a failed momentum gate cannot reuse another ticker's stale
`final_decision.json`. Review runs do not update the global dashboard or engine
run database. Historical backtests use adjusted daily bars and do not model fees
or slippage; backtest results are evidence, not forecasts.

## Execution Boundary

`execute_confirmed_trade` is the only MCP operation that can reach a broker
order path. It requires `confirm=true`; doubts require separate acknowledgement.
Each review is one-shot. Buys reuse the existing hard risk gate, buying-power
check, whitelist, kill switch, notional/sleeve checks, and one-share live ramp.
Automatic quantity resizing is disabled for this action. Robinhood receives a
pre-trade review before submission.

Sell requests are close-only: shorting is never supported, sellable shares are
verified from Robinhood, and the kill switch, close gate, whitelist and quantity
limit apply. Broker submissions are recorded by broker-reported state; queued or
unconfirmed is not called filled. If submission status is ambiguous, the review
is marked for reconciliation and must not be blindly retried.

When `SPY_LIVE` is not armed, a confirmed buy is recorded as a simulation
proposal and no broker order is submitted. The analyst recommendation itself
never places an order.

## Other Limited Actions

- `run_engine(ticker)`: refresh analysis only; no order call.
- `create_trade_proposal(...)`: record a risk-checked sim proposal, never fill it.
- `reject_trade_proposal(proposal_id, note)`: reject a pending proposal.
- `run_paper_sweep(confirm=true, limit=10)`: close only simulated journal
  positions at mechanical exits; no live reconciliation or broker order.

There is no raw `place_equity_order`, cancel, or general live-sweep tool.

## iPhone Notifications

Install the **ntfy** app from the iOS App Store, subscribe to a private topic,
and allow notifications in iOS Settings. Configure `SPY_NTFY_TOPIC` on the host
running the server; optionally set `SPY_NTFY_SERVER` (HTTPS only) and
`SPY_NTFY_TOKEN` for a protected server/topic. Without a topic, push is disabled.
Committee notifications are intentionally two concise lines; full analysis is
retrievable by `review_id`. Never put account numbers or credentials in a topic
name or notification content.

## Sutra HTTP Adapter

`cma_lab/sutra_api.py` serves the same desk functions over local HTTP so the
Sutra gateway can discover them from an Agent Manifest. The stdio server above
is unchanged.

- **Address:** `http://127.0.0.1:8790` (set `SPY_DESK_SUTRA_PORT` to change it).
  It binds to loopback only and returns 403 for any `Host` header that is not
  `127.0.0.1`, `localhost` or `[::1]` on that port.
- **Auth:** every tool call needs the header `X-Spy-Desk-Token` matching
  `SPY_DESK_TOKEN` (read with `lab_env`, so `cma_lab/.env` works). The adapter
  refuses to start without it. The manifest
  (`/.well-known/sutra-agent.json`) and `/api/health` need no token.
- **Tools:** the read-only tools listed above, plus `get_engine_run(run_id)`,
  and two confirm-first tools that return at once and finish in the background:
  - `run_engine(ticker)` returns a `run_id`; poll `get_engine_run`. Runs live
    in memory, so a restart forgets them.
  - `analyze_trade_request(...)` returns a `review_id`; poll
    `get_trade_analysis_details`.
- **Never listed:** `execute_confirmed_trade`, `run_paper_sweep`,
  `create_trade_proposal`, `reject_trade_proposal`, `wait_for_trade_analysis`.
- **Broker guard:** at start-up the adapter wraps `lab._mcp_call` so that, in
  this process, only `get_portfolio`, `get_equity_positions`,
  `get_equity_orders` and `get_equity_quotes` reach Robinhood. Any other broker
  tool, including `place_equity_order` and `review_equity_order`, raises before
  a request is sent, whichever module calls it. The one exception is
  `place_desk_order` (below), which opens an order window for its own thread
  while it runs.
- **Live trading:** the adapter never sets or changes `SPY_LIVE`.
  `/api/health` reports `live_trading_armed` (as `execution.py` computes it)
  and nothing more.

### Buying And Selling Through Sutra

Off unless `SPY_DESK_SUTRA_TRADING=1` is set when the adapter starts. Then the
manifest lists one more tool, `place_desk_order(review_id,
acknowledge_doubts?, proceed_without_analysis?)`. The flow is:

1. `analyze_trade_request(ticker, side, quantity, ...)` returns a `review_id`.
2. `get_trade_analysis_details(review_id)` shows the analysis when it's done.
3. `place_desk_order(review_id)` submits exactly that order through the desk's
   `execute_confirmed_trade`, with `confirm=true`.

Every desk check still applies: the risk gate, ticker whitelist, kill switch,
quantity and notional limits, the live ramp cap, buying power, no shorting,
and one submission per review. When live trading is not armed, a buy is only
recorded as a simulation proposal and a sell is refused. The adapter never sets
or changes `SPY_LIVE` or `SPY_SIM_ONLY`.

Sutra orders also have their own caps, read on every call:

| Variable | Meaning |
| --- | --- |
| `SPY_DESK_SUTRA_MAX_ORDER_USD` | Largest single order, in dollars (quantity × limit price or live quote). Required. |
| `SPY_DESK_SUTRA_MAX_DAILY_USD` | Total of Sutra orders per New York trading day. Required. |
| `SPY_DESK_SUTRA_MAX_DAILY_ORDERS` | Number of Sutra orders per day. Default 3. |

Without both dollar caps no order goes through, and `/api/health` reports
`degraded`. Each order is written to `cma_lab/sutra_orders.json` (gitignored)
before the broker is called. Orders that weren't submitted are released from
the caps; an order whose outcome is unclear keeps counting.

In `sutra-discover`, approve `place_desk_order` as **confirm-first**, never
read-only, so each call waits for a `gateway_confirm`. Note that Sutra accepts
that confirmation from any client holding your Sutra token, so an agent that
can call tools can also confirm them. The dollar caps are the limit that
doesn't depend on the client asking you first.

### Health

`GET /api/health` returns `status` `ok` or `degraded`, with `problems`, broker
token presence, expiry and whether it can refresh, the age of the last engine
report in hours, `live_trading_armed`, and `sutra_trading` (whether Sutra
orders are on and their dollar caps set). It holds no token values or amounts. The
status is `degraded` when the broker token is missing, or expired or within a
day of expiry with no refresh token, or when settings can't be read.

### Run It

```bash
cd cma_lab && ../.venv/bin/python sutra_api.py
```

As a service, copy `cma_lab/launchd/com.sidd.spy.sutra-api.plist` to
`~/Library/LaunchAgents/` and load it with `launchctl`. Logs go to
`~/Library/Logs/spy-sutra-api.{out,err}.log`.

### Register With Sutra

Add a source to Sutra's `gateway/discovery-sources.yaml`, put the same token
in Sutra's environment (`~/.config/sutra/sutra.env`), then run `sutra-discover`
to review and tier the tools:

```yaml
  - name: spy-desk
    manifest_url: http://127.0.0.1:8790/.well-known/sutra-agent.json
    base_url: http://127.0.0.1:8790
    auth_header: X-Spy-Desk-Token
    auth_env: SPY_DESK_TOKEN
```
