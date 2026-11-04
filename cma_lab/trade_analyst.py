"""Cached, asynchronous trade analysis for the spy-desk MCP server."""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from store import store

CMA_DIR = Path(__file__).resolve().parent
REPO_ROOT = CMA_DIR.parent
ENGINE_DIR = REPO_ROOT / "spy_decision_engine"
ENGINE_TIMEOUT_SECONDS = 600
BACKTEST_TIMEOUT_SECONDS = 300
MAX_INITIAL_WAIT_SECONDS = 120
MAX_WAIT_SECONDS = 120
BACKTEST_YEARS = 3
REVIEW_CACHE_TTL_SECONDS = 900
REVIEWS_COLLECTION = "trade_reviews"
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="spy-analyst")
_futures: dict[str, Future] = {}
_future_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _all_reviews() -> dict[str, dict[str, Any]]:
    return store().load(REVIEWS_COLLECTION, {}) or {}


def _save_review(review: dict[str, Any]) -> None:
    with store().lock(REVIEWS_COLLECTION):
        reviews = _all_reviews()
        reviews[review["review_id"]] = review
        store().save(REVIEWS_COLLECTION, reviews)


def _get_review(review_id: str) -> dict[str, Any] | None:
    return _all_reviews().get(str(review_id).strip())


def _json_report(directory: Path, name: str) -> dict[str, Any] | None:
    path = directory / f"{name}.json"
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _run_engine(ticker: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"spy-review-{ticker}-") as temp_dir:
        reports_dir = Path(temp_dir) / "reports"
        reports_dir.mkdir()
        env = os.environ.copy()
        env["TICKER"] = ticker
        env["SPY_REPORTS_DIR"] = str(reports_dir)
        env["SPY_ANALYST_RUN"] = "1"
        try:
            proc = subprocess.run(
                [sys.executable, "main.py"], cwd=ENGINE_DIR, env=env,
                capture_output=True, text=True, timeout=ENGINE_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"Engine is still running beyond {ENGINE_TIMEOUT_SECONDS}s."
            ) from exc
        if proc.returncode:
            raise RuntimeError(f"Engine failed ({proc.returncode}): {proc.stderr[-1500:]}")

        momentum = _json_report(reports_dir, "momentum")
        sentiment = _json_report(reports_dir, "sentiment")
        price = _json_report(reports_dir, "price_analysis")
        final = _json_report(reports_dir, "final_decision")
        return {
            "ticker": ticker,
            "completed_at": _now(),
            "momentum": momentum,
            "sentiment": sentiment,
            "price_analysis": price,
            "final_decision": final,
            "final_decision_fresh": final is not None,
            "engine_output_tail": proc.stdout[-2000:],
        }


def _backtest(ticker: str) -> dict[str, Any]:
    end = date.today()
    start = end.replace(year=end.year - BACKTEST_YEARS)
    with tempfile.TemporaryDirectory(prefix=f"spy-backtest-{ticker}-") as temp_dir:
        output = Path(temp_dir) / "backtest.json"
        try:
            proc = subprocess.run(
                [sys.executable, str(CMA_DIR / "backtest" / "review.py"),
                 "--ticker", ticker, "--start", start.isoformat(),
                 "--end", end.isoformat(), "--output", str(output)],
                cwd=REPO_ROOT, capture_output=True, text=True,
                timeout=BACKTEST_TIMEOUT_SECONDS, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"Backtest data fetch/replay exceeded {BACKTEST_TIMEOUT_SECONDS}s."
            ) from exc
        if proc.returncode:
            raise RuntimeError(f"Backtest failed ({proc.returncode}): {proc.stderr[-1200:]}")
        return json.loads(output.read_text())


def _make_judgment(request: dict, engine: dict, backtest: dict) -> dict[str, Any]:
    ticker, side = request["ticker"], request["side"]
    momentum = engine.get("momentum") or {}
    sentiment = engine.get("sentiment") or {}
    final = engine.get("final_decision") or {}
    overall_sentiment = (sentiment.get("overall") or {}).get("blended_score")
    if overall_sentiment is None:
        overall_sentiment = (sentiment.get("overall") or {}).get("headline_score")
    gate_passed = momentum.get("trade_allowed") is True
    engine_decision = final.get("decision") if engine.get("final_decision_fresh") else None
    trend = str(momentum.get("trend") or "UNKNOWN").upper()
    doubts: list[str] = []

    if not engine.get("final_decision_fresh"):
        doubts.append("Momentum gate stopped the engine before a fresh final decision was produced.")
    if side == "buy" and not gate_passed:
        doubts.append("The engine momentum gate does not currently allow a long entry.")
    if side == "buy" and engine_decision and "BUY" not in str(engine_decision).upper():
        doubts.append(f"Engine final signal is {engine_decision}, not BUY.")
    if side == "sell":
        doubts.append("The engine and backtest library are long-only; sell is treated only as closing verified shares, never a short.")
    if overall_sentiment is None:
        doubts.append("No sentiment score was produced.")
    elif side == "buy" and float(overall_sentiment) < 0.5:
        doubts.append(f"Sentiment is weak/negative ({float(overall_sentiment):.2f}).")

    relevant = next((r for r in backtest.get("strategies", [])
                     if r.get("strategy") == "trend_follow"), None)
    if side == "buy":
        if not relevant:
            doubts.append("No trend-follow backtest result is available for this ticker.")
        elif int(relevant.get("n", 0)) < 20:
            doubts.append(f"Trend-follow backtest sample is small (n={relevant.get('n', 0)}; need 20 for this check).")
        elif float(relevant.get("expectancy_per_trade", 0) or 0) <= 0:
            doubts.append("Trend-follow backtest expectancy is not positive over the tested period.")

    confident = side == "buy" and gate_passed and engine_decision and \
        "BUY" in str(engine_decision).upper() and overall_sentiment is not None and \
        float(overall_sentiment) >= 0.5 and relevant is not None and \
        int(relevant.get("n", 0)) >= 20 and \
        float(relevant.get("expectancy_per_trade", 0) or 0) > 0
    return {
        "label": "confident" if confident else "doubt",
        "engine_signal": engine_decision or ("NO_TRADE_MOMENTUM_GATE" if not gate_passed else "UNAVAILABLE"),
        "trend": trend,
        "sentiment_score": overall_sentiment,
        "momentum_gate_passed": gate_passed,
        "backtest_strategy": relevant,
        "doubts": doubts,
        "summary": (
            f"Evidence supports {side} {ticker}. Confirm the exact order to execute."
            if confident else
            f"I have doubts about {side} {ticker}: " + " ".join(doubts[:3])
        ),
    }


def _perform_review(review_id: str) -> dict[str, Any]:
    reviews = _all_reviews()
    review = reviews.get(review_id)
    if not review:
        return {"error": "Review request disappeared from the cache."}
    try:
        engine = _run_engine(review["request"]["ticker"])
    except Exception as exc:  # noqa: BLE001
        review = _get_review(review_id) or review
        review.update(status="analysis_error", error=str(exc), updated_at=_now())
        _save_review(review)
        return review

    try:
        backtest = _backtest(review["request"]["ticker"])
    except Exception as exc:  # noqa: BLE001
        backtest = {"error": str(exc), "strategies": []}

    judgment = _make_judgment(review["request"], engine, backtest)
    review = _get_review(review_id) or review
    review.update(
        status="complete",
        engine=engine,
        backtest=backtest,
        judgment=judgment,
        updated_at=_now(),
        cache="trade_reviews",
    )
    _save_review(review)
    return review


def start_trade_review(
    ticker: str, side: str, quantity: float, entry_style: str = "market",
    limit_price: float | None = None, wait_seconds: int = 120,
) -> dict[str, Any]:
    from risk_gate import evaluate, load_risk_config

    ticker = str(ticker).strip().upper()
    side = str(side).strip().lower()
    entry_style = str(entry_style).strip().lower()
    try:
        quantity = float(quantity)
        limit_price = float(limit_price) if limit_price is not None else None
        wait_seconds = max(0, min(int(wait_seconds), MAX_INITIAL_WAIT_SECONDS))
    except (TypeError, ValueError):
        return {"error": "quantity, limit_price, and wait_seconds must be valid numbers."}
    if not math.isfinite(quantity) or quantity <= 0:
        return {"error": "quantity must be a positive finite number."}
    if side not in {"buy", "sell"}:
        return {"error": "side must be buy or sell; shorting is not supported."}
    if entry_style not in {"market", "limit"}:
        return {"error": "entry_style must be market or limit."}
    if entry_style == "limit" and (limit_price is None or not math.isfinite(limit_price) or limit_price <= 0):
        return {"error": "limit orders require a positive finite limit_price."}
    if entry_style == "limit" and not quantity.is_integer():
        return {"error": "Robinhood does not accept fractional-share limit orders; use market or an integer quantity."}
    allowed = {s.upper() for s in load_risk_config().symbol_whitelist}
    if ticker not in allowed:
        return {"error": f"{ticker} is not in the active trade whitelist.", "allowed_symbols": sorted(allowed)}
    cfg = load_risk_config()
    if quantity > cfg.max_quantity:
        return {"error": f"Quantity {quantity:g} exceeds the active limit {cfg.max_quantity:g}."}
    if side == "buy":
        order = {"symbol": ticker, "side": side, "type": entry_style, "quantity": quantity}
        if limit_price is not None:
            order["price"] = limit_price
        gate = evaluate("place_equity_order", order, cfg)
        if not gate.allowed:
            return {"error": "Request fails the active risk gate.", "risk_gate": str(gate)}

    with _future_lock:
        cached_reviews = _all_reviews()
        request = {"ticker": ticker, "side": side, "quantity": quantity,
                   "entry_style": entry_style, "limit_price": limit_price}
        now = datetime.now(timezone.utc)
        for existing in sorted(cached_reviews.values(),
                               key=lambda item: item.get("created_at", ""), reverse=True):
            if existing.get("status") == "running":
                return {"error": "Another analysis is already running.", "review_id": existing["review_id"],
                        "message": "Wait for or retrieve that analysis before starting another."}
            if existing.get("status") == "complete" and existing.get("request") == request:
                try:
                    age = (now - datetime.fromisoformat(existing["created_at"])).total_seconds()
                except (KeyError, ValueError):
                    age = REVIEW_CACHE_TTL_SECONDS + 1
                if 0 <= age <= REVIEW_CACHE_TTL_SECONDS:
                    existing["cache_hit"] = True
                    return existing
        review_id = "rev_" + uuid.uuid4().hex[:12]
        review = {
            "review_id": review_id,
            "created_at": _now(),
            "updated_at": _now(),
            "status": "running",
            "request": request,
            "message": "Analysis runs in the background. Initial wait is capped at two minutes.",
        }
        _save_review(review)
        future = _executor.submit(_perform_review, review_id)
        _futures[review_id] = future

    try:
        future.result(timeout=wait_seconds)
    except FutureTimeout:
        review = _get_review(review_id) or review
        review["message"] = (
            "Analysis is taking over two minutes. Tell the user they can wait by requesting this review, "
            "or proceed without the analysis by explicitly confirming the exact order."
        )
        return review
    except Exception as exc:  # noqa: BLE001
        return _get_review(review_id) or {"review_id": review_id, "status": "analysis_error", "error": str(exc)}
    return _get_review(review_id) or review


def get_trade_review(review_id: str) -> dict[str, Any]:
    review = _get_review(review_id)
    if not review:
        return {"error": "Unknown review_id."}
    future = _futures.get(review_id)
    if review.get("status") == "running" and future is None:
        review.update(status="interrupted", message="The MCP server restarted before this cached analysis completed.")
        _save_review(review)
    return review


def wait_for_trade_review(review_id: str, wait_seconds: int = 120) -> dict[str, Any]:
    try:
        wait_seconds = max(0, min(int(wait_seconds), MAX_WAIT_SECONDS))
    except (TypeError, ValueError):
        return {"error": "wait_seconds must be a number from 0 to 120."}
    review = get_trade_review(review_id)
    future = _futures.get(review_id)
    if review.get("status") != "running" or future is None:
        return review
    try:
        future.result(timeout=wait_seconds)
    except FutureTimeout:
        review = _get_review(review_id) or review
        review["message"] = "Analysis is still running. Wait again or explicitly choose to proceed without it."
        return review
    except Exception as exc:  # noqa: BLE001
        return _get_review(review_id) or {"review_id": review_id, "status": "analysis_error", "error": str(exc)}
    return _get_review(review_id) or review
