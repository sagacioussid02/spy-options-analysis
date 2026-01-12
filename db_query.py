#!/usr/bin/env python3
"""
Database Query Tool - View historical engine runs, trades, and analysis
"""
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from spy_decision_engine.database import DecisionDatabase
import json

def print_header(title):
    print(f"\n{'='*100}")
    print(f"  {title}")
    print(f"{'='*100}\n")

def show_recent_runs(db, limit=10):
    """Show recent engine runs"""
    print_header(f"📊 RECENT ENGINE RUNS (Last {limit})")
    
    runs = db.get_all_runs(limit=limit)
    if not runs:
        print("  No engine runs found")
        return
    
    print(f"{'Date':<12} {'Time':<8} {'Decision':<15} {'Score':<8} {'SPY':<8} {'Recommended':<12} {'Target':<10}")
    print("-" * 100)
    
    for run in runs:
        date = run['run_date'] if run['run_date'] else 'N/A'
        time = run['run_time'] if run['run_time'] else 'N/A'
        decision = run['decision'] if run['decision'] else 'N/A'
        score = f"{run['final_score']:.1f}" if run['final_score'] else 'N/A'
        spy = f"${run['spy_price']:.2f}" if run['spy_price'] else 'N/A'
        entry = f"${run['recommended_entry']:.2f}" if run['recommended_entry'] else 'N/A'
        target = f"${run['take_profit']:.2f}" if run['take_profit'] else 'N/A'
        
        print(f"{date:<12} {time:<8} {decision:<15} {score:<8} {spy:<8} {entry:<12} {target:<10}")

def show_recent_trades(db, limit=10):
    """Show recent trades"""
    print_header(f"📈 RECENT TRADES (Last {limit})")
    
    trades = db.get_all_trades(limit=limit)
    if not trades:
        print("  No trades found")
        return
    
    print(f"{'Trade ID':<20} {'Strike':<8} {'Entry $':<10} {'Exit $':<10} {'Profit':<12} {'ROI':<8} {'Status':<8}")
    print("-" * 100)
    
    for trade in trades:
        trade_id = trade['trade_id']
        strike = f"${trade['strike']:.0f}" if trade['strike'] else 'N/A'
        entry = f"${trade['premium_paid']:.2f}" if trade['premium_paid'] else 'N/A'
        exit_p = f"${trade['premium_sold']:.2f}" if trade['premium_sold'] else 'N/A'
        profit = f"${trade['profit']:.2f}" if trade['profit'] else 'Pending'
        roi = f"{trade['profit_pct']:.1f}%" if trade['profit_pct'] else 'Pending'
        status = "CLOSED" if trade['is_open'] == 0 else "OPEN"
        
        print(f"{trade_id:<20} {strike:<8} {entry:<10} {exit_p:<10} {profit:<12} {roi:<8} {status:<8}")

def show_trade_stats(db):
    """Show overall trade statistics"""
    print_header("📊 TRADING STATISTICS")
    
    stats = db.get_trade_stats()
    if not stats or stats.get('total_trades', 0) == 0:
        print("  No closed trades yet")
        return
    
    print(f"Total Trades:         {stats.get('total_trades', 0)}")
    print(f"  Wins:               {stats.get('wins', 0)}")
    print(f"  Losses:             {stats.get('losses', 0)}")
    print(f"  Breaks:             {stats.get('breaks', 0)}")
    print()
    print(f"Win Rate:             {stats.get('win_rate', 0):.1f}%")
    print(f"Net Profit:           ${stats.get('net_profit', 0):.2f}")
    print(f"Average Profit/Trade: ${stats.get('avg_profit', 0):.2f}")
    print(f"Average ROI:          {stats.get('avg_roi', 0):.1f}%")
    print(f"Profit Factor:        {stats.get('profit_factor', 0):.2f}x")

def show_stats_by_strike(db):
    """Show win rate by strike"""
    print_header("🎯 WIN RATE BY STRIKE")
    
    strikes = db.get_win_rate_by_strike()
    if not strikes:
        print("  No data yet")
        return
    
    print(f"{'Strike':<8} {'Trades':<8} {'Wins':<8} {'Win Rate':<12} {'Total Profit':<15} {'Avg ROI':<10}")
    print("-" * 100)
    
    for strike in strikes:
        strike_price = f"${strike['strike']:.0f}" if strike['strike'] else 'N/A'
        total = strike['total']
        wins = strike['wins']
        win_rate = (wins / total * 100) if total > 0 else 0
        profit = f"${strike['total_profit']:.2f}" if strike['total_profit'] else '$0.00'
        roi = f"{strike['avg_roi']:.1f}%" if strike['avg_roi'] else '0.0%'
        
        print(f"{strike_price:<8} {total:<8} {wins:<8} {win_rate:>10.1f}% {profit:<15} {roi:<10}")

def show_stats_by_dte(db):
    """Show win rate by DTE"""
    print_header("📅 WIN RATE BY DTE (Days to Expiration)")
    
    dtes = db.get_win_rate_by_dte()
    if not dtes:
        print("  No data yet")
        return
    
    print(f"{'DTE':<8} {'Trades':<8} {'Wins':<8} {'Win Rate':<12} {'Total Profit':<15} {'Avg ROI':<10}")
    print("-" * 100)
    
    for dte in dtes:
        dte_num = f"{dte['dte']}" if dte['dte'] else 'N/A'
        total = dte['total']
        wins = dte['wins']
        win_rate = (wins / total * 100) if total > 0 else 0
        profit = f"${dte['total_profit']:.2f}" if dte['total_profit'] else '$0.00'
        roi = f"{dte['avg_roi']:.1f}%" if dte['avg_roi'] else '0.0%'
        
        print(f"{dte_num:<8} {total:<8} {wins:<8} {win_rate:>10.1f}% {profit:<15} {roi:<10}")

def show_stats_by_confidence(db):
    """Show win rate by confidence level"""
    print_header("💪 WIN RATE BY ENGINE CONFIDENCE")
    
    confidences = db.get_win_rate_by_confidence()
    if not confidences:
        print("  No data yet")
        return
    
    print(f"{'Confidence':<15} {'Trades':<8} {'Wins':<8} {'Win Rate':<12} {'Total Profit':<15} {'Avg ROI':<10}")
    print("-" * 100)
    
    for conf in confidences:
        range_text = conf['confidence_range'] if conf['confidence_range'] else 'N/A'
        total = conf['total']
        wins = conf['wins']
        win_rate = (wins / total * 100) if total > 0 else 0
        profit = f"${conf['total_profit']:.2f}" if conf['total_profit'] else '$0.00'
        roi = f"{conf['avg_roi']:.1f}%" if conf['avg_roi'] else '0.0%'
        
        print(f"{range_text:<15} {total:<8} {wins:<8} {win_rate:>10.1f}% {profit:<15} {roi:<10}")

def show_daily_performance(db, days=10):
    """Show daily performance summary"""
    print_header(f"📅 DAILY PERFORMANCE (Last {days} days)")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    perf = db.get_performance_range(
        start_date.strftime('%Y-%m-%d'),
        end_date.strftime('%Y-%m-%d')
    )
    
    if not perf:
        print("  No daily performance data yet")
        return
    
    print(f"{'Date':<12} {'Trades':<8} {'Win Rate':<12} {'Daily P&L':<12} {'Decision':<15} {'Confidence':<12}")
    print("-" * 100)
    
    for day in perf:
        date = day['trade_date']
        entered = day['trades_entered'] if day['trades_entered'] else 0
        win_rate = f"{day['daily_trades_win_rate']:.1f}%" if day['daily_trades_win_rate'] else 'N/A'
        profit = f"${day['daily_profit']:.2f}" if day['daily_profit'] else '$0.00'
        decision = day['engine_decision'] if day['engine_decision'] else 'N/A'
        confidence = f"{day['engine_confidence']:.0f}%" if day['engine_confidence'] else 'N/A'
        
        print(f"{date:<12} {entered:<8} {win_rate:<12} {profit:<12} {decision:<15} {confidence:<12}")

def show_open_trades(db):
    """Show currently open trades"""
    print_header("🔴 OPEN TRADES")
    
    trades = db.get_open_trades()
    if not trades:
        print("  No open trades")
        return
    
    print(f"{'Trade ID':<20} {'Date':<12} {'Strike':<8} {'Entry $':<10} {'# Contracts':<12} {'Days Old':<10}")
    print("-" * 100)
    
    for trade in trades:
        trade_id = trade['trade_id']
        date = trade['entry_date'] if trade['entry_date'] else 'N/A'
        strike = f"${trade['strike']:.0f}" if trade['strike'] else 'N/A'
        entry = f"${trade['premium_paid']:.2f}" if trade['premium_paid'] else 'N/A'
        contracts = trade['contracts'] if trade['contracts'] else 0
        
        # Calculate days old
        if trade['entry_date']:
            entry_dt = datetime.strptime(trade['entry_date'], '%Y-%m-%d')
            days_old = (datetime.now() - entry_dt).days
        else:
            days_old = 0
        
        print(f"{trade_id:<20} {date:<12} {strike:<8} {entry:<10} {contracts:<12} {days_old:<10}")

def export_all_data(db):
    """Export all data to JSON"""
    print_header("💾 EXPORTING DATA")
    
    filepath = db.export_to_json()
    print(f"✓ Data exported to: {filepath}")
    print()

def main():
    """Main menu"""
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
    else:
        command = None
    
    db = DecisionDatabase()
    
    if command in ['runs', 'r']:
        show_recent_runs(db, limit=20)
    elif command in ['trades', 't']:
        show_recent_trades(db, limit=20)
    elif command in ['open', 'o']:
        show_open_trades(db)
    elif command in ['stats', 's']:
        show_trade_stats(db)
    elif command in ['strike']:
        show_stats_by_strike(db)
    elif command in ['dte']:
        show_stats_by_dte(db)
    elif command in ['confidence', 'c']:
        show_stats_by_confidence(db)
    elif command in ['daily', 'd']:
        show_daily_performance(db, days=30)
    elif command in ['export', 'e']:
        export_all_data(db)
    else:
        # Show all
        print("\n" + "="*100)
        print("  SPY DECISION ENGINE - DATABASE QUERY TOOL")
        print("="*100)
        print("\nUsage: ./.venv/bin/python db_query.py [command]")
        print("\nCommands:")
        print("  runs       - Recent engine runs")
        print("  trades     - Recent trades")
        print("  open       - Open trades")
        print("  stats      - Overall statistics")
        print("  strike     - Win rate by strike")
        print("  dte        - Win rate by DTE")
        print("  confidence - Win rate by confidence level")
        print("  daily      - Daily performance summary")
        print("  export     - Export all data to JSON")
        print()
        
        # Show default dashboard
        show_recent_runs(db, limit=5)
        show_recent_trades(db, limit=5)
        show_open_trades(db)
        show_trade_stats(db)

if __name__ == '__main__':
    main()
