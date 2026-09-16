#!/usr/bin/env python3
"""
Trade Monitor: Check expiring positions and their current P&L
Shows all open BUY trades expiring in 1-2 days
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent / 'spy_decision_engine'))

from experimental.quantum_monte_carlo import QuantumMonteCarloOptions


def load_trades() -> List[Dict]:
    """Load trades from database"""
    trades_file = Path(__file__).parent / 'spy_decision_engine' / 'data' / 'trades.json'
    
    if not trades_file.exists():
        print("❌ No trades database found")
        return []
    
    with open(trades_file, 'r') as f:
        data = json.load(f)
    
    return data.get('trades', [])


def get_current_spy_price() -> float:
    """Get current SPY price from latest analysis"""
    reports_dir = Path(__file__).parent / 'spy_decision_engine' / 'reports'
    
    # Try to load from snapshot
    snapshot_file = reports_dir / 'snapshot.json'
    if snapshot_file.exists():
        with open(snapshot_file, 'r') as f:
            data = json.load(f)
            return data.get('SPY', {}).get('price', 689.58)
    
    return 689.58  # Default fallback


def days_until_expiry(expiry_date_str: str) -> int:
    """Calculate days until expiration"""
    try:
        expiry = datetime.strptime(expiry_date_str, '%Y-%m-%d')
        today = datetime(2026, 1, 7)  # Current date in simulation
        delta = (expiry - today).days
        return max(0, delta)
    except:
        return 0


def calculate_option_value(S: float, K: float, r: float = 0.045, sigma: float = 0.18, T: float = 0.01) -> float:
    """Calculate current option value using Black-Scholes"""
    try:
        qmc = QuantumMonteCarloOptions(S, K, r, sigma, T)
        result = qmc.black_scholes('call')
        return result.get('price', 0)
    except:
        return 0


def analyze_expiring_trades():
    """Main function to analyze expiring trades"""
    trades = load_trades()
    current_spy = get_current_spy_price()
    
    print("\n" + "="*100)
    print("📊 TRADE MONITOR - EXPIRING POSITIONS (1-2 Days)")
    print("="*100)
    print(f"\nCurrent SPY Price: ${current_spy:.2f}")
    print(f"Analysis Date: January 07, 2026\n")
    
    # Filter for open BUY trades expiring soon
    expiring_trades = []
    
    for trade in trades:
        # Check if trade is still open (exit is null)
        if trade.get('exit') is None:
            dte = trade.get('expiry_dte', 0)
            
            # Show trades expiring in 1-2 days
            if 0 <= dte <= 2:
                expiring_trades.append({
                    'trade': trade,
                    'dte': dte
                })
    
    if not expiring_trades:
        print("✅ No open trades expiring in 1-2 days\n")
        return
    
    # Sort by DTE (closest first)
    expiring_trades.sort(key=lambda x: x['dte'])
    
    # Display header
    print(f"{'Trade ID':<20} {'Strike':<8} {'DTE':<5} {'Entry':<8} {'Current':<8} {'Intrinsic':<10} {'P&L':<10} {'Status':<15}")
    print("-" * 100)
    
    total_pnl = 0
    total_contracts = 0
    
    for item in expiring_trades:
        trade = item['trade']
        dte = item['dte']
        
        trade_id = trade.get('trade_id', 'N/A')
        strike = trade.get('strike', 0)
        entry_data = trade.get('entry', {})
        entry_premium = entry_data.get('premium_paid', 0)
        num_contracts = entry_data.get('contracts', 1)
        
        # Calculate current value
        T = dte / 365
        current_value = calculate_option_value(current_spy, strike, T=T)
        
        # Intrinsic value
        intrinsic = max(current_spy - strike, 0)
        
        # P&L
        pnl_per_share = current_value - entry_premium
        pnl_total = pnl_per_share * 100 * num_contracts
        
        # Status
        if pnl_per_share > 0:
            status = f"✅ +{pnl_per_share:.2f}"
        elif pnl_per_share < 0:
            status = f"❌ {pnl_per_share:.2f}"
        else:
            status = "➖ Break-even"
        
        print(f"{trade_id:<20} ${strike:<7.0f} {dte:<5} ${entry_premium:<7.2f} ${current_value:<7.2f} ${intrinsic:<9.2f} ${pnl_total:<9.2f} {status:<15}")
        
        total_pnl += pnl_total
        total_contracts += num_contracts
    
    print("-" * 100)
    print(f"{'TOTAL':<20} {'':<8} {'':<5} {'':<8} {'':<8} {'':<10} ${total_pnl:<9.2f}")
    print(f"\n📈 Portfolio Summary: {total_contracts} contract(s), Total P&L: ${total_pnl:+.2f}\n")


def detailed_trade_report():
    """Show detailed report for each expiring trade"""
    trades = load_trades()
    current_spy = get_current_spy_price()
    
    # Filter expiring trades
    expiring_trades = []
    for trade in trades:
        # Check if trade is still open (exit is null)
        if trade.get('exit') is None:
            dte = trade.get('expiry_dte', 0)
            if 0 <= dte <= 2:
                expiring_trades.append((trade, dte))
    
    if not expiring_trades:
        return
    
    expiring_trades.sort(key=lambda x: x[1])
    
    for trade, dte in expiring_trades:
        print("\n" + "="*80)
        print(f"📋 DETAILED ANALYSIS: Trade {trade.get('trade_id', 'N/A')}")
        print("="*80)
        
        strike = trade.get('strike', 0)
        entry_data = trade.get('entry', {})
        entry_premium = entry_data.get('premium_paid', 0)
        entry_spy = entry_data.get('price', current_spy)
        num_contracts = entry_data.get('contracts', 1)
        
        print(f"\n🎯 POSITION DETAILS:")
        print(f"   Strike: ${strike}")
        print(f"   Entry SPY: ${entry_spy:.2f}")
        print(f"   Entry Premium: ${entry_premium:.2f}")
        print(f"   Contracts: {num_contracts}")
        print(f"   Status: OPEN")
        
        print(f"\n📊 CURRENT MARKET:")
        print(f"   Current SPY: ${current_spy:.2f}")
        print(f"   SPY Change: ${current_spy - entry_spy:+.2f} ({(current_spy/entry_spy - 1)*100:+.2f}%)")
        print(f"   DTE: {dte} day(s)")
        
        # Calculate values
        T = dte / 365
        current_value = calculate_option_value(current_spy, strike, T=T)
        intrinsic = max(current_spy - strike, 0)
        time_value = max(current_value - intrinsic, 0)
        
        pnl_per_share = current_value - entry_premium
        pnl_total = pnl_per_share * 100 * num_contracts
        pnl_pct = (pnl_per_share / entry_premium) * 100 if entry_premium > 0 else 0
        
        print(f"\n💰 OPTION VALUATION:")
        print(f"   Current Option Price: ${current_value:.2f}")
        print(f"   Intrinsic Value: ${intrinsic:.2f}")
        print(f"   Time Value: ${time_value:.2f}")
        print(f"   Entry Premium: ${entry_premium:.2f}")
        
        print(f"\n📈 YOUR P&L:")
        print(f"   Gain/Loss per Share: ${pnl_per_share:+.2f} ({pnl_pct:+.1f}%)")
        print(f"   Total Gain/Loss: ${pnl_total:+.2f}")
        
        # Break-even analysis
        breakeven = strike + entry_premium
        print(f"\n🎯 BREAK-EVEN & RISK:")
        print(f"   Break-even Price: ${breakeven:.2f}")
        print(f"   Current SPY: ${current_spy:.2f}")
        
        if current_spy > breakeven:
            cushion = current_spy - breakeven
            print(f"   ✅ SAFE: Can drop ${cushion:.2f} and still break even")
        else:
            risk = breakeven - current_spy
            print(f"   ⚠️  AT RISK: Only ${risk:.2f} cushion to break-even")
        
        # Exit scenarios
        print(f"\n🔮 EXIT SCENARIOS (with {dte} day(s) left):")
        
        if dte == 0:
            print(f"   AT EXPIRATION: Option worth = ${intrinsic:.2f}")
            if current_spy > strike:
                print(f"   ✅ ITM: You get ${intrinsic:.2f} per share")
            else:
                print(f"   ❌ OTM: You get $0 (total loss)")
        else:
            # Scenario: SPY up 1%
            spy_up = current_spy * 1.01
            val_up = calculate_option_value(spy_up, strike, T=T)
            pnl_up = (val_up - entry_premium) * 100 * num_contracts
            
            print(f"   If SPY +1% (${spy_up:.2f}): Option ~${val_up:.2f}, P&L: ${pnl_up:+.2f}")
            
            # Scenario: SPY down 1%
            spy_down = current_spy * 0.99
            val_down = calculate_option_value(spy_down, strike, T=T)
            pnl_down = (val_down - entry_premium) * 100 * num_contracts
            
            print(f"   If SPY -1% (${spy_down:.2f}): Option ~${val_down:.2f}, P&L: ${pnl_down:+.2f}")
        
        # Recommendation
        print(f"\n💡 RECOMMENDATION:")
        if pnl_per_share > 0:
            print(f"   ✅ CONSIDER EXITING: You have ${pnl_per_share:.2f}/share profit")
            print(f"   With only {dte} day(s) left, time decay is accelerating")
            print(f"   Lock in your gains before overnight risk")
        elif pnl_per_share < -0.20:
            print(f"   ❌ WATCH CLOSELY: You're down ${abs(pnl_per_share):.2f}/share")
            print(f"   With {dte} day(s) left, limited time to recover")
            print(f"   Consider exit if SPY drops further")
        else:
            print(f"   ⏳ HOLD OR SMALL EXIT: Nearly break-even")
            print(f"   With {dte} day(s) left, decision depends on market view")


def main():
    """Run all analyses"""
    analyze_expiring_trades()
    detailed_trade_report()
    
    print("\n" + "="*80)
    print("✅ Trade monitor complete")
    print("="*80 + "\n")


if __name__ == '__main__':
    main()
