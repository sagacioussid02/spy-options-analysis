"""
Option Pricing Helper
Converts stock price targets to option premium targets
"""
import json
import math
from pathlib import Path

class OptionPricingHelper:
    """
    Maps stock price movements to option premium movements
    Uses Black-Scholes approximation for quick estimates
    """
    
    def __init__(self, volatility=0.25, risk_free_rate=0.05):
        """
        Initialize option pricer
        volatility: Annual volatility (0.25 = 25% IV)
        """
        self.volatility = volatility
        self.risk_free_rate = risk_free_rate
    
    def load_volatility_from_engine(self, volatility_json_path):
        """Load actual volatility from engine output"""
        try:
            with open(volatility_json_path) as f:
                vol_data = json.load(f)
                # Get IV from volatility data
                self.volatility = vol_data.get('iv_percentile', 0.25) / 100
                return self.volatility
        except:
            pass
        return self.volatility
    
    def black_scholes_call(self, S, K, T, r=None, sigma=None):
        """
        Black-Scholes call price
        S: Current stock price
        K: Strike price
        T: Time to expiration (in years, e.g., 2/365 for 2 days)
        r: Risk-free rate
        sigma: Volatility
        """
        if r is None:
            r = self.risk_free_rate
        if sigma is None:
            sigma = self.volatility
        
        if T <= 0:
            return max(S - K, 0)
        
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        
        N_d1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
        N_d2 = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
        
        call = S * N_d1 - K * math.exp(-r * T) * N_d2
        return max(call, 0.01)
    
    def black_scholes_put(self, S, K, T, r=None, sigma=None):
        """Black-Scholes put price"""
        if r is None:
            r = self.risk_free_rate
        if sigma is None:
            sigma = self.volatility
        
        if T <= 0:
            return max(K - S, 0)
        
        call = self.black_scholes_call(S, K, T, r, sigma)
        put = call - S + K * math.exp(-r * T)
        return max(put, 0.01)
    
    def estimate_premium_at_price(self, strike, entry_price, target_price, dte=2, direction='UP'):
        """
        Estimate what option premium should be at target price
        
        Example:
            You buy 690 call at $2.50 when SPY=$689
            What's the premium if SPY hits $692 (target)?
            → ~$4.13
        
        Args:
            strike: Strike price (e.g., 690)
            entry_price: Stock price when you buy option (e.g., 689)
            target_price: Stock price target (e.g., 692)
            dte: Days to expiration
            direction: 'UP' for calls, 'DOWN' for puts
        """
        # Years to expiration
        T = dte / 365.0
        
        if direction == 'UP':
            # Call option
            entry_premium = self.black_scholes_call(entry_price, strike, T)
            target_premium = self.black_scholes_call(target_price, strike, T)
        else:
            # Put option
            entry_premium = self.black_scholes_put(entry_price, strike, T)
            target_premium = self.black_scholes_put(target_price, strike, T)
        
        return {
            'entry_premium': round(entry_premium, 2),
            'target_premium': round(target_premium, 2),
            'profit_per_contract': round((target_premium - entry_premium) * 100, 2),
            'roi': round((target_premium / entry_premium - 1) * 100, 1) if entry_premium > 0 else 0,
            'breakeven_stock_price': round(strike + entry_premium, 2)
        }
    
    def premium_table(self, current_price, target_price, dte=2, direction='UP'):
        """
        Generate a table of option premiums for different strikes
        
        Shows: "If SPY goes from $689 to $692 (target), here's what happens to each option"
        """
        results = []
        
        # Generate strikes: ATM, +1, +2, +3, -1, -2 strikes away
        strikes = [
            int(current_price) - 2,
            int(current_price) - 1,
            int(current_price),      # ATM
            int(current_price) + 1,
            int(current_price) + 2,
            int(current_price) + 3,
        ]
        
        for strike in strikes:
            pricing = self.estimate_premium_at_price(strike, current_price, target_price, dte, direction)
            
            # Categorize strike
            if strike == int(current_price):
                category = "ATM (At Money)"
            elif strike < int(current_price):
                category = f"ITM (In Money) -{int(current_price) - strike}"
            else:
                category = f"OTM (Out Money) +{strike - int(current_price)}"
            
            results.append({
                'strike': strike,
                'category': category,
                'entry_premium': pricing['entry_premium'],
                'target_premium': pricing['target_premium'],
                'profit_per_contract': pricing['profit_per_contract'],
                'roi': pricing['roi'],
                'breakeven': pricing['breakeven_stock_price']
            })
        
        return results
    
    def print_premium_table(self, current_price, target_price, dte=2, direction='UP'):
        """Pretty print the premium table"""
        table = self.premium_table(current_price, target_price, dte, direction)
        
        direction_text = "CALLS (Bullish)" if direction == 'UP' else "PUTS (Bearish)"
        print(f"\n{'='*100}")
        print(f"📊 OPTION PREMIUM TABLE ({direction_text})")
        print(f"   Current SPY: ${current_price:.2f} → Target: ${target_price:.2f} ({dte} DTE)")
        print(f"{'='*100}\n")
        print(f"{'Strike':<8} {'Category':<20} {'Entry $':<12} {'Target $':<12} {'Profit/$':<12} {'ROI':<10} {'B/E Stock':<12}")
        print("-" * 100)
        
        for row in table:
            print(f"${row['strike']:<7} {row['category']:<20} ${row['entry_premium']:<11.2f} "
                  f"${row['target_premium']:<11.2f} ${row['profit_per_contract']:<11.2f} "
                  f"{row['roi']:>8.1f}% ${row['breakeven']:<11.2f}")
        
        print(f"\n{'='*100}\n")
        print("KEY:")
        print("  Entry $: Premium when you BUY (at current stock price)")
        print("  Target $: Premium when stock hits TARGET (potential profit level)")
        print("  Profit/$: Dollar profit per contract if you exit at target")
        print("  ROI: Return on investment %")
        print("  B/E Stock: Stock price needed to break even at expiration")
        print()
    
    def recommendation(self, current_price, target_price, dte=2, direction='UP'):
        """Recommend which strike to buy"""
        table = self.premium_table(current_price, target_price, dte, direction)
        
        # Find ATM strike
        atm_index = None
        for i, row in enumerate(table):
            if 'ATM' in row['category']:
                atm_index = i
                break
        
        if atm_index is None:
            return None
        
        atm = table[atm_index]
        otm_1 = table[atm_index + 1] if atm_index + 1 < len(table) else None
        
        rec = {
            'best_strike': atm['strike'],
            'reason': 'ATM (At the Money) - best balance of cost & profit potential',
            'entry_price': atm['entry_premium'],
            'target_profit': atm['profit_per_contract'],
            'roi': atm['roi'],
            'alternative': None
        }
        
        if otm_1:
            rec['alternative'] = {
                'strike': otm_1['strike'],
                'reason': 'OTM (+1) - cheaper, higher ROI, but needs bigger move',
                'entry_price': otm_1['entry_premium'],
                'target_profit': otm_1['profit_per_contract'],
                'roi': otm_1['roi']
            }
        
        return rec


def analyze_current_decision():
    """Analyze current final_decision.json and show option premiums"""
    decision_path = Path(__file__).parent.parent / 'reports' / 'final_decision.json'
    volatility_path = Path(__file__).parent.parent / 'reports' / 'volatility.json'
    
    try:
        with open(decision_path) as f:
            decision = json.load(f)
        
        # Initialize pricer
        pricer = OptionPricingHelper()
        pricer.load_volatility_from_engine(volatility_path)
        
        # Get key values
        current_price = decision['market_conditions']['spy_price']
        recommended_entry = decision['entry_strategy']['recommended_entry']
        take_profit = decision['risk_reward']['take_profit_target']
        direction = 'UP' if 'BUY' in decision['decision'] else 'DOWN'
        dte = 2  # Default to 2 DTE
        
        print(f"\n{'='*100}")
        print(f"🎯 OPTION PRICING ANALYSIS")
        print(f"{'='*100}\n")
        print(f"Engine Decision: {decision['decision']}")
        print(f"Confidence: {decision['confidence_score'] if 'confidence_score' in decision else decision['final_score']}%")
        print(f"Current SPY: ${current_price}")
        print(f"Recommended Entry (Stock): ${recommended_entry}")
        print(f"Take Profit Target (Stock): ${take_profit}")
        print(f"Direction: {direction}")
        print()
        
        # Show premium table
        pricer.print_premium_table(current_price, take_profit, dte, direction)
        
        # Show recommendation
        rec = pricer.recommendation(current_price, take_profit, dte, direction)
        if rec:
            print(f"📈 RECOMMENDED STRIKE")
            print(f"   Strike: ${rec['best_strike']}")
            print(f"   Entry Premium: ${rec['entry_price']:.2f}/contract")
            print(f"   Expected Profit (at target): ${rec['target_profit']:.2f}/contract")
            print(f"   Expected ROI: {rec['roi']:.1f}%")
            print(f"   Reasoning: {rec['reason']}")
            
            if rec['alternative']:
                alt = rec['alternative']
                print(f"\n   Alternative: ${alt['strike']} strike")
                print(f"   Entry Premium: ${alt['entry_price']:.2f}/contract (cheaper)")
                print(f"   Expected Profit: ${alt['target_profit']:.2f}/contract")
                print(f"   Expected ROI: {alt['roi']:.1f}%")
                print(f"   Reasoning: {alt['reason']}")
        
        print(f"\n{'='*100}\n")
        
        return pricer
    
    except Exception as e:
        print(f"Error: {e}")
        return OptionPricingHelper()


if __name__ == '__main__':
    analyze_current_decision()
