#!/usr/bin/env python3
"""
Test script: Compare Quantum MC vs Classical MC vs Black-Scholes
For your SPY trading decisions
"""

import sys
import json
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent / 'spy_decision_engine'))

from utils.quantum_monte_carlo import QuantumMonteCarloOptions, print_comparison


def test_spy_current_trade():
    """Test the SPY $688 Call that you bought"""
    print("\n🚀 TESTING YOUR CURRENT TRADE: SPY $688 Call")
    
    S = 689.56      # Your entry price
    K = 688         # Strike
    r = 0.045       # 4.5% annual rate
    sigma = 0.18    # 18% volatility
    T = 2/365       # 2 days to expiration
    
    results = print_comparison(S, K, r, sigma, T, 'call')
    
    # Ensure reports directory exists
    reports_dir = Path(__file__).parent / 'spy_decision_engine' / 'reports'
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    # Save results
    output_file = reports_dir / 'quantum_mc_spy_current.json'
    with open(output_file, 'w') as f:
        # Convert results to JSON-serializable format
        json_results = {
            'trade_info': {
                'symbol': 'SPY',
                'strike': K,
                'type': 'call',
                'entry_price': S,
                'dte': 2
            },
            'market_parameters': {
                'stock_price': S,
                'strike': K,
                'volatility': sigma,
                'risk_free_rate': r,
                'time_to_expiry_years': T,
                'time_to_expiry_days': int(T * 365)
            },
            'pricing_methods': {}
        }
        
        for method, data in results['methods'].items():
            json_results['pricing_methods'][method] = data
        
        json.dump(json_results, f, indent=2)
    
    print(f"\n✅ Results saved to: {output_file}")
    return results


def test_multiple_strikes():
    """Test quantum pricing across multiple strikes"""
    print("\n📊 TESTING QUANTUM PRICING ACROSS MULTIPLE STRIKES")
    
    S = 689.56
    r = 0.045
    sigma = 0.18
    T = 2/365
    
    strikes = [685, 687, 688, 689, 691, 693]
    
    print("\nStrike | BS Price | Class MC | Quantum MC | BS vs CMC Diff | BS vs QMC Diff")
    print("-" * 80)
    
    results_by_strike = {}
    
    # Ensure reports directory exists
    reports_dir = Path(__file__).parent / 'spy_decision_engine' / 'reports'
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    for K in strikes:
        qmc = QuantumMonteCarloOptions(S, K, r, sigma, T)
        
        bs = qmc.black_scholes('call')['price']
        cmc = qmc.classical_monte_carlo(5000, 'call')['price']
        
        # Try quantum (may fail if Qiskit not installed)
        try:
            qmc_res = qmc.quantum_monte_carlo_simple(3, 'call')
            qmc_price = qmc_res.get('price', 'N/A')
        except:
            qmc_price = 'N/A'
        
        bs_cmc_diff = abs(bs - cmc) if isinstance(cmc, float) else 'N/A'
        bs_qmc_diff = abs(bs - qmc_price) if isinstance(qmc_price, float) else 'N/A'
        
        print(f"${K:>3d}   | ${bs:>7.4f} | ${cmc:>7.4f} | ${str(qmc_price):>8s} | ${str(bs_cmc_diff):>12s} | ${str(bs_qmc_diff):>12s}")
        
        results_by_strike[K] = {
            'black_scholes': bs,
            'classical_mc': cmc,
            'quantum_mc': qmc_price
        }
    
    # Save multi-strike results
    output_file = reports_dir / 'quantum_mc_multi_strike.json'
    with open(output_file, 'w') as f:
        json.dump({
            'stock_price': S,
            'volatility': sigma,
            'dte': 2,
            'results_by_strike': results_by_strike
        }, f, indent=2)
    
    print(f"\n✅ Multi-strike results saved to: {output_file}")


def test_different_dte():
    """Test quantum pricing across different days to expiration"""
    print("\n📅 TESTING QUANTUM PRICING ACROSS DIFFERENT DTEs")
    
    S = 689.56
    K = 688
    r = 0.045
    sigma = 0.18
    
    dtes = [1, 2, 3, 5, 7, 14, 30]
    
    print("\nDTE | BS Price | Class MC | Quantum MC | BS vs CMC Diff")
    print("-" * 70)
    
    results_by_dte = {}
    
    # Ensure reports directory exists
    reports_dir = Path(__file__).parent / 'spy_decision_engine' / 'reports'
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    for dte in dtes:
        T = dte / 365
        qmc = QuantumMonteCarloOptions(S, K, r, sigma, T)
        
        bs = qmc.black_scholes('call')['price']
        cmc = qmc.classical_monte_carlo(5000, 'call')['price']
        
        # Try quantum
        try:
            qmc_res = qmc.quantum_monte_carlo_simple(3, 'call')
            qmc_price = qmc_res.get('price', 'N/A')
        except:
            qmc_price = 'N/A'
        
        bs_cmc_diff = abs(bs - cmc) if isinstance(cmc, float) else 'N/A'
        
        print(f"{dte:>3d} | ${bs:>7.4f} | ${cmc:>7.4f} | ${str(qmc_price):>8s} | ${str(bs_cmc_diff):>12s}")
        
        results_by_dte[dte] = {
            'black_scholes': bs,
            'classical_mc': cmc,
            'quantum_mc': qmc_price,
            'theta_daily': (bs - qmc.black_scholes('call')['theta'])
        }
    
    # Save DTE results
    output_file = reports_dir / 'quantum_mc_by_dte.json'
    with open(output_file, 'w') as f:
        json.dump({
            'stock_price': S,
            'strike': K,
            'volatility': sigma,
            'results_by_dte': results_by_dte
        }, f, indent=2)
    
    print(f"\n✅ DTE results saved to: {output_file}")


def test_volatility_sensitivity():
    """Test how quantum pricing changes with volatility"""
    print("\n📈 TESTING QUANTUM SENSITIVITY TO VOLATILITY CHANGES")
    
    S = 689.56
    K = 688
    r = 0.045
    T = 2/365
    
    vols = [0.10, 0.15, 0.18, 0.20, 0.25, 0.30]
    
    print("\nVol   | BS Price | Class MC | Quantum MC | Vega (Price/Vol)")
    print("-" * 70)
    
    results_by_vol = {}
    
    # Ensure reports directory exists
    reports_dir = Path(__file__).parent / 'spy_decision_engine' / 'reports'
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    for vol in vols:
        qmc = QuantumMonteCarloOptions(S, K, r, vol, T)
        
        bs = qmc.black_scholes('call')['price']
        bs_full = qmc.black_scholes('call')
        cmc = qmc.classical_monte_carlo(5000, 'call')['price']
        
        # Try quantum
        try:
            qmc_res = qmc.quantum_monte_carlo_simple(3, 'call')
            qmc_price = qmc_res.get('price', 'N/A')
        except:
            qmc_price = 'N/A'
        
        vega = bs_full.get('vega', 'N/A')
        
        print(f"{vol*100:>4.0f}% | ${bs:>7.4f} | ${cmc:>7.4f} | ${str(qmc_price):>8s} | {str(vega):>14s}")
        
        results_by_vol[vol] = {
            'black_scholes': bs,
            'classical_mc': cmc,
            'quantum_mc': qmc_price,
            'vega': bs_full.get('vega', None)
        }
    
    # Save volatility results
    output_file = reports_dir / 'quantum_mc_by_volatility.json'
    with open(output_file, 'w') as f:
        json.dump({
            'stock_price': S,
            'strike': K,
            'dte': 2,
            'results_by_volatility': results_by_vol
        }, f, indent=2)
    
    print(f"\n✅ Volatility results saved to: {output_file}")


def main():
    """Run all tests"""
    print("=" * 80)
    print("QUANTUM MONTE CARLO OPTIONS PRICING - TEST SUITE")
    print("=" * 80)
    
    try:
        test_spy_current_trade()
    except Exception as e:
        print(f"⚠️  Error in test_spy_current_trade: {e}")
    
    try:
        test_multiple_strikes()
    except Exception as e:
        print(f"⚠️  Error in test_multiple_strikes: {e}")
    
    try:
        test_different_dte()
    except Exception as e:
        print(f"⚠️  Error in test_different_dte: {e}")
    
    try:
        test_volatility_sensitivity()
    except Exception as e:
        print(f"⚠️  Error in test_volatility_sensitivity: {e}")
    
    print("\n" + "=" * 80)
    print("✅ TEST SUITE COMPLETE")
    print("=" * 80)
    print("\n📊 Check the 'reports' folder for detailed JSON results:")
    print("  - quantum_mc_spy_current.json (your current trade)")
    print("  - quantum_mc_multi_strike.json (different strikes)")
    print("  - quantum_mc_by_dte.json (different expirations)")
    print("  - quantum_mc_by_volatility.json (sensitivity to volatility)")


if __name__ == '__main__':
    main()
