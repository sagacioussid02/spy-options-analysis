#!/usr/bin/env python3
"""
Command-line tool for managing trades.
Make it easy to record entries and exits.

Usage:
    python trade_cmd.py add --strike 690 --dte 2 --entry 688.69 --premium 2.50
    python trade_cmd.py close --id 2026-01-07-001 --exit 692.32 --premium-sold 4.13
    python trade_cmd.py list
    python trade_cmd.py analyze
    python trade_cmd.py summary
"""
import argparse
import sys
import os
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from spy_decision_engine.utils.trade_tracker import TradeTracker
from spy_decision_engine.utils.trade_analyzer import TradeAnalyzer
from spy_decision_engine.database import DecisionDatabase


def cmd_add(args):
    """Add a new trade entry."""
    tracker = TradeTracker()
    db = DecisionDatabase()
    
    # Get current time if not provided
    entry_time = args.entry_time or datetime.now().strftime("%H:%M")
    entry_date = datetime.now().strftime("%Y-%m-%d")
    
    # Read engine confidence from final_decision.json if available
    engine_confidence = args.confidence
    if engine_confidence is None:
        try:
            import json
            with open('spy_decision_engine/reports/final_decision.json', 'r') as f:
                decision = json.load(f)
                engine_confidence = decision.get('final_score', 75.0)
        except:
            engine_confidence = 75.0
    
    trade_id = tracker.add_trade(
        instrument=args.instrument or "SPY Call",
        strike=args.strike,
        expiry_dte=args.dte,
        entry_price=args.entry,
        entry_time=entry_time,
        premium_paid=args.premium,
        contracts=args.contracts or 10,
        engine_confidence=engine_confidence,
        engine_recommendation=args.reason or "Trade recommendation",
        predicted_direction=args.direction or "UP",
        reason_for_entry=args.reason or "Short-term directional bias"
    )
    
    # Also save to database
    db.add_trade({
        'id': trade_id,
        'entry_date': entry_date,
        'entry_time': entry_time,
        'instrument': args.instrument or 'SPY Call',
        'strike': args.strike,
        'dte': args.dte,
        'direction': args.direction or 'UP',
        'entry_price': args.entry,
        'premium_paid': args.premium,
        'contracts': args.contracts or 10,
        'engine_confidence': engine_confidence,
        'reason': args.reason or 'Trade recommendation'
    })
    
    print(f"\n✓ Trade added: {trade_id}")
    print(f"  Instrument: {args.instrument or 'SPY Call'}")
    print(f"  Strike: ${args.strike}")
    print(f"  DTE: {args.dte}")
    print(f"  Entry: ${args.entry} @ {entry_time}")
    print(f"  Premium: ${args.premium}")
    print(f"  Contracts: {args.contracts or 10}")
    print(f"  Confidence: {engine_confidence}%")
    print(f"  ✓ Saved to database\n")


def cmd_close(args):
    """Close an open trade."""
    tracker = TradeTracker()
    db = DecisionDatabase()
    
    exit_time = args.exit_time or datetime.now().strftime("%H:%M")
    exit_date = datetime.now().strftime("%Y-%m-%d")
    
    success = tracker.close_trade(
        trade_id=args.id,
        exit_price=args.exit,
        exit_time=exit_time,
        premium_sold=args.premium_sold,
        reason_for_exit=args.reason or "Manual exit"
    )
    
    if success:
        # Also save to database
        db.close_trade(args.id, {
            'exit_date': exit_date,
            'exit_time': exit_time,
            'exit_price': args.exit,
            'premium_sold': args.premium_sold
        })
        
        print(f"\n✓ Trade {args.id} closed")
        print(f"  Exit: ${args.exit} @ {exit_time}")
        print(f"  Premium Sold: ${args.premium_sold}")
        
        # Show trade details
        for trade in tracker.get_trades(closed_only=True):
            if trade["trade_id"] == args.id:
                print(f"  Profit: ${trade['exit']['profit']:.2f} ({trade['exit']['profit_pct']:.1f}%)")
                if trade.get("analysis"):
                    print(f"  Result: {trade['analysis']['lesson']}")
        print(f"  ✓ Saved to database\n")
    else:
        print(f"✗ Could not close trade {args.id}")


def cmd_list(args):
    """List trades."""
    tracker = TradeTracker()
    
    if args.open:
        trades = tracker.get_open_trades()
        print(f"\n📂 OPEN TRADES ({len(trades)})\n")
    else:
        trades = tracker.get_trades()
        print(f"\n📂 ALL TRADES ({len(trades)})\n")
    
    for trade in trades:
        print(f"  {trade['trade_id']}: {trade['instrument']} {trade['strike']} ({trade['expiry_dte']} DTE)")
        print(f"    Entry: ${trade['entry']['price']} @ {trade['entry']['time']}")
        
        if trade['exit']:
            print(f"    Exit: ${trade['exit']['price']} @ {trade['exit']['time']}")
            print(f"    P&L: ${trade['exit']['profit']:.2f} ({trade['exit']['profit_pct']:.1f}%)")
        else:
            print(f"    Status: OPEN")
        print()


def cmd_summary(args):
    """Show trading summary."""
    tracker = TradeTracker()
    tracker.print_summary()


def cmd_analyze(args):
    """Analyze trades and show recommendations."""
    analyzer = TradeAnalyzer()
    
    if len(analyzer.closed_trades) == 0:
        print("\n✗ No closed trades yet. Record some trades first!\n")
        return
    
    analyzer.print_report()
    
    recommendations = analyzer.get_recommendations()
    print("\n\n🎯 NEXT TRADE RECOMMENDATIONS")
    print("=" * 70)
    for rule in recommendations['trading_rules']:
        print(f"  • {rule}")
    print("\n" + "=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Trade management tool for SPY options"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Add trade
    add_parser = subparsers.add_parser("add", help="Add a new trade")
    add_parser.add_argument("--strike", type=int, required=True, help="Strike price")
    add_parser.add_argument("--dte", type=int, required=True, help="Days to expiry (1-4)")
    add_parser.add_argument("--entry", type=float, required=True, help="SPY entry price")
    add_parser.add_argument("--premium", type=float, required=True, help="Premium paid per contract")
    add_parser.add_argument("--contracts", type=int, help="Number of contracts (default: 10)")
    add_parser.add_argument("--instrument", help="SPY Call or SPY Put (default: SPY Call)")
    add_parser.add_argument("--time", dest="entry_time", help="Entry time HH:MM (default: now)")
    add_parser.add_argument("--direction", help="Predicted direction: UP or DOWN")
    add_parser.add_argument("--reason", help="Reason for entry")
    add_parser.add_argument("--confidence", type=float, help="Engine confidence override")
    add_parser.set_defaults(func=cmd_add)
    
    # Close trade
    close_parser = subparsers.add_parser("close", help="Close an open trade")
    close_parser.add_argument("--id", required=True, help="Trade ID to close")
    close_parser.add_argument("--exit", type=float, required=True, help="SPY exit price")
    close_parser.add_argument("--premium-sold", type=float, required=True, help="Premium sold per contract")
    close_parser.add_argument("--time", dest="exit_time", help="Exit time HH:MM (default: now)")
    close_parser.add_argument("--reason", help="Reason for exit")
    close_parser.set_defaults(func=cmd_close)
    
    # List trades
    list_parser = subparsers.add_parser("list", help="List all trades")
    list_parser.add_argument("--open", action="store_true", help="Show only open trades")
    list_parser.set_defaults(func=cmd_list)
    
    # Summary
    summary_parser = subparsers.add_parser("summary", help="Show trading summary")
    summary_parser.set_defaults(func=cmd_summary)
    
    # Analyze
    analyze_parser = subparsers.add_parser("analyze", help="Analyze trades and get recommendations")
    analyze_parser.set_defaults(func=cmd_analyze)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    args.func(args)


if __name__ == "__main__":
    main()
