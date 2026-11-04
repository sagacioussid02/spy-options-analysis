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
