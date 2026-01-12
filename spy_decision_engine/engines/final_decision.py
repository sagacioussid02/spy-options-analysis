"""
Final Decision Engine

Aggregates all engine outputs and produces final recommendation.
Includes comprehensive analysis: sentiment per stock, risk/reward, Greeks estimates,
position sizing, exit strategy, and upcoming catalysts.
"""
import json
import os
from typing import Dict, List

from context.market_context import MarketContext
from utils.scoring import calculate_final_score, score_to_decision
import config


class FinalDecisionEngine:
    """Aggregates all engine signals and produces comprehensive final decision."""
    
    def run(self, context: MarketContext) -> None:
        """
        Execute final decision analysis.
        
        Args:
            context: Shared market context with all engine results
        """
        # Extract scores from context
        momentum_score = context.spy_momentum.get("score", 0.0)
        alignment_score = context.market_snapshot.get("alignment_score", 0.5)
        
        # Use blended sentiment if available, otherwise fall back to headline sentiment
        overall_data = context.news_sentiment.get("overall", {})
        if "blended_score" in overall_data:
            overall_sentiment = overall_data.get("blended_score", 0.5)
        else:
            overall_sentiment = overall_data.get("score", 0.5)
        
        volatility_penalty = context.volatility.get("penalty", 0.0)
        event_driven_score = context.event_driven.get("score", 0.5) if hasattr(context, 'event_driven') else 0.5
        
        # Get holdings analysis score
        holdings_score = self._get_holdings_analysis_score()
        
        # Calculate final score
        final_score = calculate_final_score(
            momentum_score,
            alignment_score,
            overall_sentiment,
            volatility_penalty,
            event_driven_score,
            holdings_score
        )
        
        # Convert score to decision
        decision, confidence = score_to_decision(final_score)
        
        # Build comprehensive output
        output = {
            "timestamp": context.market_snapshot.get("timestamp", ""),
            "final_score": round(final_score, 1),
            "decision": decision,
            "confidence": confidence,
            
            # Component scores
            "component_scores": {
                "momentum": round(momentum_score, 2),
                "alignment": round(alignment_score, 2),
                "event_driven": round(event_driven_score, 2),
                "sentiment_overall": round(overall_sentiment, 2),
                "volatility_penalty": round(volatility_penalty, 2),
                "holdings_analysis": round(holdings_score, 2),
            },
            
            # Market conditions
            "market_conditions": {
                "spy_price": context.spy_momentum.get("indicators", {}).get("current_price", 0),
                "trend": context.spy_momentum.get("trend", "NEUTRAL"),
                "rsi": context.spy_momentum.get("rsi", 50),
                "ema_9": context.spy_momentum.get("indicators", {}).get("ema_9", 0),
                "ema_21": context.spy_momentum.get("indicators", {}).get("ema_21", 0),
                "vwap": context.spy_momentum.get("indicators", {}).get("vwap", 0),
                "vix": context.volatility.get("vix", 15),
            },
            
            # Per-stock sentiment breakdown
            "stock_sentiment_analysis": self._build_stock_sentiment(context),
            
            # Entry strategy
            "entry_strategy": {
                "conservative_entry": context.price_analysis.get("entry_prices", {}).get("conservative"),
                "current_entry": context.price_analysis.get("entry_prices", {}).get("at_current"),
                "risky_entry": context.price_analysis.get("entry_prices", {}).get("risky"),
                "recommended_entry": self._recommend_entry(context),
            },
            
            # Position sizing
            "position_management": {
                "size_recommendation": context.price_analysis.get("position_sizing", {}).get("position_size_pct"),
                "volatility_adjusted": context.price_analysis.get("position_sizing", {}).get("rationale"),
                "risk_per_trade": self._calculate_risk_per_trade(context),
            },
            
            # Options Greeks (estimated)
            "options_greeks": self._estimate_greeks(context),
            
            # Event-driven analysis
            "event_analysis": self._build_event_analysis(context),
            
            # Risk/Reward analysis
            "risk_reward": {
                "entry_price": context.price_analysis.get("entry_prices", {}).get("at_current"),
                "take_profit_target": self._calculate_take_profit(context),
                "stop_loss_level": self._calculate_stop_loss(context),
                "risk_reward_ratio": self._calculate_rr_ratio(context),
            },
            
            # Time decay considerations
            "time_decay": {
                "days_to_expiry": self._days_to_expiry(context),
                "theta_daily": self._estimate_theta(context),
                "theta_warning": "High" if self._estimate_theta(context) > 0.5 else "Moderate",
            },
            
            # Key bullish factors
            "bullish_factors": self._get_bullish_factors(context),
            
            # Key bearish factors
            "bearish_factors": self._get_bearish_factors(context),
            
            # Confidence indicators
            "confidence_score": {
                "value": round(self._calculate_confidence(context), 2),
                "drivers": self._confidence_drivers(context),
            },
            
            # Upcoming catalysts placeholder
            "upcoming_catalysts": {
                "note": "Check PREDICTION_MARKETS.md for event catalysts",
                "next_steps": "1. Monitor NVIDIA earnings (Jan 29), 2. Track Fed decisions, 3. Watch AI sector news"
            },
            
            # Final recommendation
            "recommendation": {
                "action": decision,
                "buy_decision": context.price_analysis.get("buy_decision", {}),
                "explanation": self._build_explanation(context, decision),
                "next_review": "Monitor momentum and sentiment daily; reassess if RSI crosses 70 or 30"
            },
            
            # Specific options to buy
            "options_what_if": context.options_whatif.get("recommended_contract", {}) if hasattr(context, 'options_whatif') else {}
        }
        
        # Write to context
        context.final_decision = output
        
        # Write to JSON file
        self._write_report(output)
        
        # Return the output for use by calling functions
        return output
    
    def _build_stock_sentiment(self, context: MarketContext) -> Dict:
        """Extract per-stock sentiment scores from sentiment analysis."""
        by_stock = context.news_sentiment.get("by_stock", {})
        return {
            stock: {
                "score": data.get("score", 0.5),
                "mentions": data.get("mentions", 0),
                "positive": data.get("positive", 0),
                "negative": data.get("negative", 0),
            }
            for stock, data in sorted(by_stock.items(), key=lambda x: x[1].get("score", 0.5), reverse=True)
        }
    
    def _recommend_entry(self, context: MarketContext) -> float:
        """Recommend best entry price based on all factors."""
        current_price = context.price_analysis.get("current_price", 0)
        sentiment = context.news_sentiment.get("overall", {}).get("score", 0.5)
        rsi = context.spy_momentum.get("rsi", 50)
        
        # If sentiment is very positive and RSI not overbought, buy at market
        if sentiment > 0.7 and rsi < 70:
            return current_price
        # If RSI overbought, wait for pullback to support
        elif rsi > 70:
            return context.price_analysis.get("technical_levels", {}).get("support", current_price)
        # Default to conservative entry
        else:
            return context.price_analysis.get("entry_prices", {}).get("conservative", current_price)
    
    def _calculate_risk_per_trade(self, context: MarketContext) -> float:
        """Calculate risk per trade in dollars (1-2% of typical account)."""
        current_price = context.price_analysis.get("current_price", 0)
        support = context.price_analysis.get("technical_levels", {}).get("support", 0)
        risk_points = current_price - support
        
        # Assume $50k account, 1% risk
        account_size = 50000
        max_risk = account_size * 0.01
        
        # Calculate position size
        if risk_points > 0:
            shares = max_risk / risk_points
            return round(shares * current_price, 2)
        return 500.0  # Default small position
    
    def _estimate_greeks(self, context: MarketContext) -> Dict:
        """Estimate options Greeks based on available data."""
        # These are rough estimates
        return {
            "delta": 0.65,  # ATM call roughly 0.5-0.7
            "gamma": 0.008,  # ATM call 
            "theta": -0.05,  # Daily theta decay
            "vega": 0.15,  # Sensitivity to VIX
            "note": "These are estimates; actual Greeks depend on exact strike and DTE"
        }
    
    def _calculate_take_profit(self, context: MarketContext) -> float:
        """Calculate take profit target."""
        current = context.price_analysis.get("current_price", 0)
        resistance = context.price_analysis.get("technical_levels", {}).get("resistance", 0)
        
        # Take profit at resistance
        return round(resistance, 2)
    
    def _calculate_stop_loss(self, context: MarketContext) -> float:
        """Calculate stop loss level."""
        current = context.price_analysis.get("current_price", 0)
        support = context.price_analysis.get("technical_levels", {}).get("support", 0)
        
        # Stop loss 3% below support or at support
        stop_loss = support * 0.97
        return round(stop_loss, 2)
    
    def _calculate_rr_ratio(self, context: MarketContext) -> str:
        """Calculate risk/reward ratio."""
        entry = self._recommend_entry(context)
        tp = self._calculate_take_profit(context)
        sl = self._calculate_stop_loss(context)
        
        if entry == 0 or sl == 0:
            return "N/A"
        
        profit = tp - entry
        risk = entry - sl
        
        if risk == 0:
            return "Infinite"
        
        ratio = profit / risk
        return f"1:{round(ratio, 2)}"
    
    def _days_to_expiry(self, context: MarketContext) -> int:
        """Estimate days to options expiry."""
        # Typically trade 7-30 DTE
        return 7
    
    def _estimate_theta(self, context: MarketContext) -> float:
        """Estimate daily theta decay."""
        # Per $100 of premium, roughly 5-10% decay per day for close to expiry
        premium = context.options_whatif.get("current_premium", 5.5) if hasattr(context, 'options_whatif') else 5.5
        return round(premium * 0.08, 3)  # Rough 8% daily decay
    
    def _get_bullish_factors(self, context: MarketContext) -> List[str]:
        """List all bullish signals."""
        factors = []
        
        if context.spy_momentum.get("trend") == "BULLISH":
            factors.append(f"Bullish trend (EMA-9: {context.spy_momentum.get('indicators', {}).get('ema_9', 0):.2f})")
        
        if context.spy_momentum.get("ema_cross"):
            factors.append("EMA-9 above EMA-21 (bullish cross)")
        
        if context.spy_momentum.get("above_vwap"):
            factors.append("Price above VWAP (bullish)")
        
        rsi = context.spy_momentum.get("rsi", 50)
        if 50 <= rsi <= 70:
            factors.append(f"RSI in sweet spot: {rsi:.1f} (not overbought)")
        
        sentiment = context.news_sentiment.get("overall", {}).get("score", 0.5)
        if sentiment > 0.6:
            factors.append(f"Positive sentiment: {sentiment:.2f}")
        
        green_count = context.market_snapshot.get("green_count", 0)
        if green_count >= 4:
            factors.append(f"Top holdings positive ({green_count}/8 green)")
        
        return factors
    
    def _get_bearish_factors(self, context: MarketContext) -> List[str]:
        """List all bearish signals."""
        factors = []
        
        if context.spy_momentum.get("trend") != "BULLISH":
            factors.append("Bearish/neutral trend")
        
        rsi = context.spy_momentum.get("rsi", 50)
        if rsi > 70:
            factors.append(f"RSI overbought: {rsi:.1f} (pullback risk)")
        elif rsi < 30:
            factors.append(f"RSI oversold: {rsi:.1f} (bounce risk)")
        
        sentiment = context.news_sentiment.get("overall", {}).get("score", 0.5)
        if sentiment < 0.4:
            factors.append(f"Negative sentiment: {sentiment:.2f}")
        
        vix = context.volatility.get("vix", 15)
        if vix > 20:
            factors.append(f"Elevated VIX: {vix:.1f} (volatility risk)")
        
        return factors
    
    def _calculate_confidence(self, context: MarketContext) -> float:
        """Calculate overall confidence in the decision."""
        # Base on number of aligned factors
        confidence = 0
        
        # Momentum aligned
        if context.spy_momentum.get("trend") == "BULLISH":
            confidence += 25
        
        # Price action aligned
        if context.spy_momentum.get("ema_cross") and context.spy_momentum.get("above_vwap"):
            confidence += 25
        
        # Sentiment aligned
        if context.news_sentiment.get("overall", {}).get("score", 0.5) > 0.6:
            confidence += 20
        
        # Holdings aligned
        if context.market_snapshot.get("alignment_score", 0) > 0.6:
            confidence += 15
        
        # RSI not extreme
        rsi = context.spy_momentum.get("rsi", 50)
        if 40 <= rsi <= 70:
            confidence += 15
        
        return min(confidence, 100)
    
    def _confidence_drivers(self, context: MarketContext) -> List[str]:
        """List what drives confidence up or down."""
        drivers = []
        
        if context.spy_momentum.get("trade_allowed"):
            drivers.append("✓ Momentum gate passed")
        else:
            drivers.append("✗ Momentum gate failed (lower confidence)")
        
        alignment = context.market_snapshot.get("alignment_score", 0)
        if alignment > 0.6:
            drivers.append(f"✓ Strong alignment: {alignment:.2f}")
        elif alignment < 0.4:
            drivers.append(f"✗ Weak alignment: {alignment:.2f}")
        
        return drivers
    
    def _build_explanation(self, context: MarketContext, decision: str) -> List[str]:
        """Build human-readable explanation for the decision."""
        explanation = []
        
        # Momentum signal
        if context.spy_momentum.get("trend") == "BULLISH":
            explanation.append("SPY momentum is bullish (EMA + VWAP aligned)")
        else:
            explanation.append("SPY momentum is bearish (conditions not met)")
        
        # Market alignment
        alignment = context.market_snapshot.get("alignment_score", 0)
        if alignment > 0.7:
            explanation.append("Top holdings are well-aligned and positive")
        elif alignment > 0.5:
            explanation.append("Mixed signals from top holdings")
        else:
            explanation.append("Top holdings showing divergence")
        
        # Sentiment - use blended_score which combines headlines + FinBert analysis
        overall_sentiment_data = context.news_sentiment.get("overall", {})
        sentiment = overall_sentiment_data.get("blended_score", 
                  overall_sentiment_data.get("headline_score", 0.5))
        
        if sentiment > 0.7:
            explanation.append("News sentiment is strongly positive")
        elif sentiment > 0.55:
            explanation.append("News sentiment is positive")
        elif sentiment < 0.3:
            explanation.append("News sentiment is strongly negative")
        elif sentiment < 0.45:
            explanation.append("News sentiment is negative")
        else:
            explanation.append("News sentiment is neutral")
        
        # Volatility
        if context.volatility.get("options_favorable", True):
            explanation.append("Volatility environment is favorable for options")
        else:
            explanation.append("Volatility is elevated - consider smaller position")
        
        return explanation
    
    def _build_event_analysis(self, context: MarketContext) -> Dict:
        """Build event-driven analysis summary"""
        if not hasattr(context, 'event_driven'):
            return {"status": "No events detected", "impact": "NEUTRAL"}
        
        events = context.event_driven
        
        return {
            "status": f"{len(events.get('events_detected', []))} events detected",
            "net_bias": events.get("net_event_bias", "NEUTRAL"),
            "confidence": events.get("confidence", "LOW"),
            "score": round(events.get("score", 0.5), 2),
            "impact_summary": events.get("impact_summary", "Mixed signals"),
        }
    
    def _write_report(self, output: Dict) -> None:
        """Write final decision report to JSON file and human-readable summary."""
        report_path = os.path.join(config.REPORTS_DIR, "final_decision.json")
        with open(report_path, "w") as f:
            json.dump(output, f, indent=2)
        print(f"✓ Final Decision report written to {report_path}")
        
        # Also write human-readable summary
        summary_path = os.path.join(config.REPORTS_DIR, "final_decision_summary.txt")
        self._write_summary(output, summary_path)
    
    def _write_summary(self, output: Dict, summary_path: str) -> None:
        """Write layman-friendly summary of the decision."""
        from datetime import datetime
        
        decision = output.get("decision", "HOLD")
        score = output.get("final_score", 50)
        confidence = output.get("confidence", "UNKNOWN")
        timestamp = output.get("timestamp", "N/A")
        
        # Format date and time nicely
        now = datetime.now()
        date_str = now.strftime("%B %d, %Y")  # e.g., "January 7, 2026"
        time_str = now.strftime("%I:%M %p")   # e.g., "12:42 PM"
        display_timestamp = f"{date_str} - {time_str}"
        
        summary = []
        summary.append("=" * 70)
        summary.append(f"SPY OPTIONS TRADING DECISION - {display_timestamp}")
        summary.append("=" * 70)
        summary.append("")
        
        # Main Decision
        summary.append(f"📊 DECISION: {decision}")
        summary.append(f"   Score: {score}/100")
        summary.append(f"   Confidence: {confidence}")
        summary.append("")
        
        # What does this mean?
        decision_meaning = {
            "BUY": "✅ CONDITIONS ARE FAVORABLE - Consider buying call options",
            "BUY SMALL": "✅ WEAK BUY - Buy small position if comfortable",
            "HOLD": "⏸️  NEUTRAL - Wait for clearer signal before trading",
            "SELL SMALL": "⚠️  WEAK SELL - Small short position only",
            "SELL": "❌ CONDITIONS ARE UNFAVORABLE - Avoid buying, consider selling"
        }
        summary.append("What it means:")
        summary.append(f"  {decision_meaning.get(decision, 'Monitor market conditions')}")
        summary.append("")
        
        # SPECIFIC OPTIONS TO BUY - Get from options report
        summary.append("🎯 SPECIFIC OPTIONS TO BUY (FASTEST CHOICE)")
        summary.append("-" * 70)
        options_data = output.get("options_what_if", {})
        if options_data:
            strike = options_data.get("strike", "N/A")
            expiry = options_data.get("expiry", "N/A")
            current_premium = options_data.get("current_premium", "N/A")
            bid = options_data.get("bid_ask", {}).get("bid", "N/A")
            ask = options_data.get("bid_ask", {}).get("ask", "N/A")
            
            # Calculate DTE (days to expiration)
            from datetime import datetime
            try:
                expiry_date = datetime.strptime(expiry, "%Y-%m-%d")
                dte = (expiry_date - now).days
            except:
                dte = "N/A"
            
            summary.append(f"  Strike Price: ${strike}")
            summary.append(f"  Expiration: {expiry} ({dte} days)")
            summary.append(f"  Current Premium: ${current_premium}")
            summary.append(f"  Bid/Ask: ${bid} / ${ask}")
            summary.append("")
            summary.append("  HOW TO BUY:")
            summary.append(f"    1. Open your broker (Tastytrade, Robinhood, etc.)")
            summary.append(f"    2. Search for 'SPY ${strike} Call {expiry}'")
            summary.append(f"    3. Buy at price between ${bid} and ${ask}")
            summary.append(f"    4. Set limit buy at ${bid} (to get best price)")
            summary.append("")
            
            # Show profit scenarios
            profit_scenarios = options_data.get("profit_if_bought", {})
            if profit_scenarios:
                summary.append("  PROFIT SCENARIOS:")
                for days_out, profit_price in sorted(profit_scenarios.items()):
                    summary.append(f"    • If SPY goes up over {days_out}: Premium could be ${profit_price}")
                summary.append("")
        else:
            # Try to load from JSON file directly if not in output
            try:
                import json
                import os
                options_file = os.path.join(os.path.dirname(__file__), '..', 'reports', 'options.json')
                if os.path.exists(options_file):
                    with open(options_file, 'r') as f:
                        options_json = json.load(f)
                    
                    strike = options_json.get("strike", "N/A")
                    expiry = options_json.get("expiry", "N/A")
                    current_premium = options_json.get("current_premium", "N/A")
                    bid = options_json.get("bid_ask", {}).get("bid", "N/A")
                    ask = options_json.get("bid_ask", {}).get("ask", "N/A")
                    
                    # Calculate DTE
                    from datetime import datetime
                    try:
                        expiry_date = datetime.strptime(expiry, "%Y-%m-%d")
                        dte = (expiry_date - now).days
                    except:
                        dte = "N/A"
                    
                    summary.append(f"  🎯 BUY THIS OPTION (Recommended):")
                    summary.append(f"     Strike: ${strike} Call")
                    summary.append(f"     Expires: {expiry} ({dte} days from now)")
                    summary.append(f"     Current Price: ${current_premium}")
                    summary.append(f"     Bid/Ask: ${bid} / ${ask}")
                    summary.append("")
                    summary.append("  HOW TO BUY IN YOUR BROKER:")
                    summary.append(f"    1. Open Tastytrade, Robinhood, or your broker app")
                    summary.append(f"    2. Search for: SPY ${strike} Call {expiry}")
                    summary.append(f"    3. Click BUY CALL")
                    summary.append(f"    4. Enter quantity (e.g., 1 contract)")
                    summary.append(f"    5. Set limit order at ${bid} (to get the best price)")
                    summary.append(f"    6. Click SEND ORDER")
                    summary.append("")
                    
                    # Show profit scenarios
                    profit_scenarios = options_json.get("profit_if_bought", {})
                    if profit_scenarios:
                        summary.append("  📈 EXPECTED PROFIT if SPY goes UP:")
                        for days_out, profit_price in sorted(profit_scenarios.items()):
                            days_num = days_out.replace('D-', '')
                            summary.append(f"     {days_num} day(s) from now: Premium could be ${profit_price} (was ${current_premium})")
                        summary.append("")
            except:
                summary.append("  (Options data loading...)")
                summary.append("")
        
        # Entry & Exit Prices for SPY stock (reference)
        summary.append("💰 SPY STOCK PRICE REFERENCE (For Context)")
        summary.append("-" * 70)
        entry = output.get("entry_strategy", {})
        if entry.get("current_entry"):
            summary.append(f"  Conservative Entry: ${entry.get('conservative_entry', 'N/A')}")
            summary.append(f"  Current Entry: ${entry.get('current_entry', 'N/A')}")
            summary.append(f"  Aggressive Entry: ${entry.get('risky_entry', 'N/A')}")
        
        exit_s = output.get("exit_strategy", {})
        if exit_s.get("take_profit_2pct"):
            summary.append(f"  Take Profit Target: ${exit_s.get('take_profit_2pct', 'N/A')} (+2%)")
            summary.append(f"  Stop Loss: ${exit_s.get('stop_loss_max', 'N/A')} (max loss)")
        summary.append("")
        
        # Why? (Key Reasons)
        summary.append("🔍 WHY THIS DECISION?")
        summary.append("-" * 70)
        
        components = output.get("component_scores", {})
        summary.append(f"  Momentum: {components.get('momentum', 'N/A')}/100 - {'Strong' if components.get('momentum', 0) > 0.6 else ('Weak' if components.get('momentum', 0) < 0.4 else 'Neutral')}")
        summary.append(f"  Sentiment: {components.get('sentiment_overall', 'N/A')} - {'Positive' if components.get('sentiment_overall', 0) > 0.6 else ('Negative' if components.get('sentiment_overall', 0) < 0.4 else 'Neutral')}")
        summary.append(f"  Market Alignment: {components.get('alignment', 'N/A')}/100 - {'Well aligned' if components.get('alignment', 0) > 0.7 else ('Mixed' if components.get('alignment', 0) > 0.5 else 'Diverging')}")
        summary.append(f"  Volatility Impact: -{components.get('volatility_penalty', 0)} penalty")
        if components.get('event_driven'):
            summary.append(f"  Events: {components.get('event_driven', 'N/A')}/100")
        summary.append("")
        
        # Market Conditions
        summary.append("📈 CURRENT MARKET CONDITIONS")
        summary.append("-" * 70)
        conditions = output.get("market_conditions", {})
        summary.append(f"  SPY Price: ${conditions.get('spy_price', 'N/A')}")
        summary.append(f"  Trend: {conditions.get('trend', 'N/A')}")
        summary.append(f"  RSI: {conditions.get('rsi', 'N/A')} (below 30=oversold, above 70=overbought)")
        summary.append(f"  VIX: {conditions.get('vix', 'N/A')} (higher=more fear)")
        summary.append("")
        
        # Bullish Factors
        bullish = output.get("bullish_factors", [])
        if bullish:
            summary.append("✅ BULLISH FACTORS (Reasons to Buy)")
            summary.append("-" * 70)
            for factor in bullish[:5]:  # Top 5
                summary.append(f"  • {factor}")
            summary.append("")
        
        # Bearish Factors
        bearish = output.get("bearish_factors", [])
        if bearish:
            summary.append("❌ BEARISH FACTORS (Reasons to Be Cautious)")
            summary.append("-" * 70)
            for factor in bearish[:5]:  # Top 5
                summary.append(f"  • {factor}")
            summary.append("")
        
        # Options Greeks
        summary.append("⚡ OPTIONS CONSIDERATIONS")
        summary.append("-" * 70)
        greeks = output.get("greeks_estimates", {})
        summary.append(f"  Time Decay (Theta): {greeks.get('theta_per_day', 'N/A')}/day")
        summary.append(f"  Delta (Price Sensitivity): {greeks.get('delta_estimate', 'N/A')}")
        summary.append(f"  Implied Volatility: {greeks.get('iv_estimate', 'N/A')}")
        summary.append("")
        
        # Action Items
        summary.append("📋 ACTION ITEMS FOR TODAY")
        summary.append("-" * 70)
        if decision in ["BUY", "BUY SMALL"]:
            summary.append("  1. Look for entry signal around the 'Current Entry Price'")
            summary.append("  2. Set limit buy order at entry price")
            summary.append("  3. Set stop loss at the 'Stop Loss' level")
            summary.append("  4. Take profits at 'Take Profit Target'")
        elif decision == "HOLD":
            summary.append("  1. Monitor SPY price - wait for clearer signal")
            summary.append("  2. Watch sentiment and momentum for changes")
            summary.append("  3. Don't force a trade - better opportunities tomorrow")
        elif decision in ["SELL", "SELL SMALL"]:
            summary.append("  1. Avoid buying calls - market looks weak")
            summary.append("  2. If holding positions, consider taking profits")
            summary.append("  3. Wait for momentum to turn positive")
        summary.append("")
        
        # Key Catalysts
        summary.append("📅 UPCOMING CATALYSTS TO WATCH")
        summary.append("-" * 70)
        summary.append("  • NVIDIA earnings: Jan 29, 2026")
        summary.append("  • Fed decision: Jan 28, 2026")
        summary.append("  • Other tech earnings throughout January")
        summary.append("  • Monitor news_sentiment.json for live updates")
        summary.append("")
        
        # Confidence Breakdown
        summary.append("💡 CONFIDENCE BREAKDOWN")
        summary.append("-" * 70)
        confidence_score = output.get("confidence_score", {})
        drivers = confidence_score.get("drivers", [])
        for driver in drivers[:5]:  # Top 5 drivers
            summary.append(f"  • {driver}")
        summary.append("")
        
        # How to use this
        summary.append("📖 HOW TO USE THIS REPORT")
        summary.append("-" * 70)
        summary.append("  1. Read the DECISION at the top")
        summary.append("  2. Check WHY (look at the reasons)")
        summary.append("  3. Use the Entry & Exit prices for your trade")
        summary.append("  4. Follow the ACTION ITEMS for today")
        summary.append("  5. If you take a trade, record it with: trade_cmd.py add ...")
        summary.append("")
    
    def _get_holdings_analysis_score(self) -> float:
        """
        Load top 5 holdings analysis and return aggregate score (0-1).
        
        Returns:
            float: Normalized holdings score (0-1)
        """
        holdings_path = os.path.join(
            config.REPORTS_DIR,
            "top_5_holdings",
            "top_5_comparison.json"
        )
        
        try:
            if not os.path.exists(holdings_path):
                # Default to neutral if no holdings analysis yet
                return 0.5
            
            with open(holdings_path, "r") as f:
                holdings_data = json.load(f)
            
            # Extract average score from holdings data
            stats = holdings_data.get("statistics", {})
            avg_score = stats.get("average_score", 50.0)
            
            # Normalize to 0-1 range
            normalized_score = avg_score / 100.0
            
            return round(normalized_score, 2)
        
        except Exception as e:
            print(f"Warning: Could not load holdings analysis: {e}")
            return 0.5
        
        # Files Reference
        summary.append("📁 DETAILED FILES FOR MORE INFO")
        summary.append("-" * 70)
        summary.append("  • final_decision.json - Full technical analysis (JSON format)")
        summary.append("  • sentiment.json - News sentiment breakdown by stock")
        summary.append("  • event_driven.json - Market-moving events detected")
        summary.append("  • momentum.json - SPY momentum analysis")
        summary.append("")
        
        summary.append("=" * 70)
        summary.append(f"Generated: {output.get('timestamp', 'N/A')}")
        summary.append("=" * 70)
        
        with open(summary_path, "w") as f:
            f.write("\n".join(summary))
        
        print(f"✓ Human-readable summary written to {summary_path}")
