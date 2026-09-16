#!/usr/bin/env python3
"""
Options Volume & Open Interest Tracker
Tracks volume and open interest for option contracts over ±3 day windows
Helps identify liquidity, momentum, and reversal signals
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
import statistics


class VolumeLiquidityTracker:
    """Track volume and open interest for options contracts."""
    
    def __init__(self, data_dir: str = None, reports_dir: str = None):
        """Initialize tracker."""
        if data_dir is None:
            data_dir = str(Path(__file__).parent.parent / "data")
        if reports_dir is None:
            reports_dir = str(Path(__file__).parent.parent / "reports")
        
        self.data_dir = Path(data_dir)
        self.reports_dir = Path(reports_dir)
        self.volume_history_file = self.data_dir / "volume_history.json"
        self.liquidity_file = self.reports_dir / "liquidity_analysis.json"
    
    def load_volume_history(self) -> dict:
        """Load historical volume/OI data."""
        if self.volume_history_file.exists():
            with open(self.volume_history_file) as f:
                return json.load(f)
        return {"contracts": {}}
    
    def record_volume_snapshot(self, ticker: str, strike: float, contract_type: str, 
                             volume: int, open_interest: int, date: str = None) -> None:
        """Record volume and open interest snapshot for a contract."""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        history = self.load_volume_history()
        
        contract_key = f"{ticker}_{strike}_{contract_type}"
        
        if contract_key not in history["contracts"]:
            history["contracts"][contract_key] = {
                "ticker": ticker,
                "strike": strike,
                "type": contract_type,
                "snapshots": []
            }
        
        history["contracts"][contract_key]["snapshots"].append({
            "date": date,
            "volume": volume,
            "open_interest": open_interest,
            "timestamp": datetime.now().isoformat()
        })
        
        with open(self.volume_history_file, 'w') as f:
            json.dump(history, f, indent=2)
    
    def get_volume_trend(self, ticker: str, strike: float, contract_type: str, 
                        days: int = 3) -> dict:
        """Get volume trend for past N days."""
        history = self.load_volume_history()
        contract_key = f"{ticker}_{strike}_{contract_type}"
        
        if contract_key not in history["contracts"]:
            return {"available": False, "message": f"No data for {contract_key}"}
        
        snapshots = history["contracts"][contract_key]["snapshots"]
        
        # Get snapshots from last N days
        cutoff_date = (datetime.now() - timedelta(days=days)).date()
        recent = [
            s for s in snapshots 
            if datetime.strptime(s["date"], "%Y-%m-%d").date() >= cutoff_date
        ]
        
        if not recent:
            return {"available": False, "message": f"No data in last {days} days"}
        
        volumes = [s["volume"] for s in recent]
        ois = [s["open_interest"] for s in recent]
        
        # Calculate trends
        if len(volumes) >= 2:
            vol_trend = "INCREASING" if volumes[-1] > volumes[0] else "DECREASING"
            vol_change_pct = ((volumes[-1] - volumes[0]) / volumes[0] * 100) if volumes[0] > 0 else 0
        else:
            vol_trend = "UNKNOWN"
            vol_change_pct = 0
        
        if len(ois) >= 2:
            oi_trend = "INCREASING" if ois[-1] > ois[0] else "DECREASING"
            oi_change_pct = ((ois[-1] - ois[0]) / ois[0] * 100) if ois[0] > 0 else 0
        else:
            oi_trend = "UNKNOWN"
            oi_change_pct = 0
        
        return {
            "available": True,
            "contract": contract_key,
            "period_days": days,
            "snapshots_count": len(recent),
            "latest_snapshot": recent[-1] if recent else None,
            "volume": {
                "current": volumes[-1] if volumes else 0,
                "previous": volumes[0] if volumes else 0,
                "average": statistics.mean(volumes) if volumes else 0,
                "trend": vol_trend,
                "change_pct": vol_change_pct,
            },
            "open_interest": {
                "current": ois[-1] if ois else 0,
                "previous": ois[0] if ois else 0,
                "average": statistics.mean(ois) if ois else 0,
                "trend": oi_trend,
                "change_pct": oi_change_pct,
            },
            "liquidity_signal": self._get_liquidity_signal(vol_trend, oi_trend, vol_change_pct, oi_change_pct)
        }
    
    def _get_liquidity_signal(self, vol_trend: str, oi_trend: str, 
                            vol_change: float, oi_change: float) -> dict:
        """Generate liquidity signal based on trends."""
        signals = []
        
        # Volume signals
        if vol_trend == "INCREASING" and vol_change > 10:
            signals.append({"type": "VOLUME_SURGE", "strength": "strong", "meaning": "High interest in contract"})
        elif vol_trend == "INCREASING":
            signals.append({"type": "VOLUME_INCREASING", "strength": "moderate", "meaning": "Growing interest"})
        elif vol_trend == "DECREASING" and vol_change < -20:
            signals.append({"type": "VOLUME_COLLAPSE", "strength": "strong", "meaning": "Interest fading"})
        
        # Open interest signals
        if oi_trend == "INCREASING" and oi_change > 10:
            signals.append({"type": "OI_ACCUMULATION", "strength": "strong", "meaning": "New positions being built"})
        elif oi_trend == "DECREASING" and oi_change < -10:
            signals.append({"type": "OI_DISTRIBUTION", "strength": "moderate", "meaning": "Positions being unwound"})
        
        # Combined signals
        if vol_trend == "INCREASING" and oi_trend == "INCREASING":
            signals.append({"type": "MOMENTUM_BUILDING", "strength": "strong", "meaning": "Both interest and positions growing"})
        elif vol_trend == "DECREASING" and oi_trend == "DECREASING":
            signals.append({"type": "MOMENTUM_FADING", "strength": "moderate", "meaning": "Interest declining"})
        
        return {
            "signals": signals,
            "overall_sentiment": "BULLISH" if len([s for s in signals if "INCREASING" in s.get("type", "")]) > 0 else "BEARISH" if len([s for s in signals if "DECREASING" in s.get("type", "")]) > 0 else "NEUTRAL"
        }
    
    def compare_strike_liquidity(self, ticker: str, strikes: list, 
                               contract_type: str = "CALL") -> dict:
        """Compare liquidity across different strikes."""
        comparison = {}
        
        for strike in strikes:
            trend = self.get_volume_trend(ticker, strike, contract_type)
            comparison[strike] = {
                "volume": trend.get("volume", {}).get("current", 0),
                "open_interest": trend.get("open_interest", {}).get("current", 0),
                "liquidity_signal": trend.get("liquidity_signal", {}),
            }
        
        # Rank by volume
        ranked = sorted(comparison.items(), key=lambda x: x[1]["volume"], reverse=True)
        
        return {
            "ticker": ticker,
            "type": contract_type,
            "comparison": comparison,
            "ranked_by_volume": [{"strike": k, "volume": v["volume"]} for k, v in ranked],
            "most_liquid": ranked[0][0] if ranked else None,
            "least_liquid": ranked[-1][0] if ranked else None,
        }
    
    def analyze_volume_for_trade(self, ticker: str, strike: float, 
                                contract_type: str = "CALL") -> dict:
        """Analyze if volume/OI is good for this trade."""
        trend = self.get_volume_trend(ticker, strike, contract_type, days=3)
        
        if not trend.get("available"):
            return {
                "analysis": "INSUFFICIENT_DATA",
                "recommendation": "Track volume first",
                "confidence": 0,
                "note": "Need ±3 days of data to analyze"
            }
        
        vol = trend["volume"]
        oi = trend["open_interest"]
        signals = trend["liquidity_signal"]["signals"]
        
        # Liquidity score (0-100)
        liquidity_score = min(100, (oi["current"] / 1000) + (vol["current"] / 1000))
        
        # Volume trend score
        vol_score = 75 if vol["trend"] == "INCREASING" else 50 if vol["trend"] == "UNKNOWN" else 25
        
        # OI trend score
        oi_score = 75 if oi["trend"] == "INCREASING" else 50 if oi["trend"] == "UNKNOWN" else 25
        
        overall_score = (liquidity_score * 0.4 + vol_score * 0.3 + oi_score * 0.3)
        
        # Recommendation
        if overall_score > 70 and vol["trend"] == "INCREASING":
            recommendation = "✅ GOOD - High liquidity, strong volume"
            analysis = "FAVORABLE"
        elif overall_score > 50 and len(signals) > 0:
            recommendation = "🟡 ACCEPTABLE - Moderate liquidity"
            analysis = "NEUTRAL"
        elif overall_score < 40:
            recommendation = "❌ POOR - Low liquidity, avoid"
            analysis = "UNFAVORABLE"
        else:
            recommendation = "⚠️  MARGINAL - Watch volume trend"
            analysis = "MARGINAL"
        
        return {
            "contract": f"{ticker}_{strike}_{contract_type}",
            "analysis": analysis,
            "liquidity_score": overall_score,
            "volume_trend": vol["trend"],
            "volume_change_pct": vol["change_pct"],
            "oi_trend": oi["trend"],
            "oi_change_pct": oi["change_pct"],
            "signals": signals,
            "recommendation": recommendation,
            "confidence": min(trend.get("snapshots_count", 1) / 3, 1.0),  # Max confidence at 3 days
            "note": f"Based on {trend.get('snapshots_count', 1)} snapshots over {trend.get('period_days', 0)} days"
        }
    
    def generate_liquidity_report(self) -> str:
        """Generate comprehensive liquidity report."""
        history = self.load_volume_history()
        
        report = f"""
╔═══════════════════════════════════════════════════════════════════╗
║          OPTIONS VOLUME & LIQUIDITY ANALYSIS REPORT               ║
║                  {datetime.now().strftime('%Y-%m-%d %H:%M')}                           
╚═══════════════════════════════════════════════════════════════════╝

📊 TRACKED CONTRACTS: {len(history.get('contracts', {}))}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        for contract_key, data in history.get("contracts", {}).items():
            trend = self.get_volume_trend(
                data["ticker"], 
                data["strike"], 
                data["type"]
            )
            
            if not trend.get("available"):
                continue
            
            analysis = self.analyze_volume_for_trade(
                data["ticker"],
                data["strike"],
                data["type"]
            )
            
            report += f"""
{contract_key}:
  Latest Volume: {trend['volume']['current']:,} (was {trend['volume']['previous']:,})
  Volume Trend: {trend['volume']['trend']} ({trend['volume']['change_pct']:+.1f}%)
  
  Open Interest: {trend['open_interest']['current']:,} (was {trend['open_interest']['previous']:,})
  OI Trend: {trend['open_interest']['trend']} ({trend['open_interest']['change_pct']:+.1f}%)
  
  Liquidity Score: {analysis['liquidity_score']:.0f}/100
  Recommendation: {analysis['recommendation']}
  
"""
        
        return report
    
    def save_analysis(self):
        """Save liquidity analysis to file."""
        history = self.load_volume_history()
        analysis = {}
        
        for contract_key, data in history.get("contracts", {}).items():
            contract_analysis = self.analyze_volume_for_trade(
                data["ticker"],
                data["strike"],
                data["type"]
            )
            analysis[contract_key] = contract_analysis
        
        analysis["timestamp"] = datetime.now().isoformat()
        analysis["total_contracts"] = len(analysis)
        
        with open(self.liquidity_file, 'w') as f:
            json.dump(analysis, f, indent=2)
        
        return str(self.liquidity_file)


# Integration with behavioral analytics
def enhance_trade_with_volume_analysis(trade_data: dict, tracker: VolumeLiquidityTracker) -> dict:
    """Add volume/OI analysis to trade data."""
    ticker = trade_data.get("ticker", "SPY")
    strike = trade_data.get("strike", 0)
    contract_type = trade_data.get("type", "CALL")
    
    volume_analysis = tracker.analyze_volume_for_trade(ticker, strike, contract_type)
    
    # Enhance trade with volume data
    trade_data["volume_analysis"] = volume_analysis
    trade_data["liquidity_score"] = volume_analysis.get("liquidity_score", 0)
    
    return trade_data


if __name__ == "__main__":
    tracker = VolumeLiquidityTracker()
    
    # Example: Record some volume snapshots
    print("Recording volume snapshots...")
    
    # SPY $700 Call example
    tracker.record_volume_snapshot("SPY", 700, "CALL", volume=15000, open_interest=45000)
    tracker.record_volume_snapshot("SPY", 700, "CALL", volume=18500, open_interest=48000)
    tracker.record_volume_snapshot("SPY", 700, "CALL", volume=21000, open_interest=52000)
    
    # Analyze
    print("\nAnalyzing liquidity...")
    analysis = tracker.analyze_volume_for_trade("SPY", 700, "CALL")
    print(f"Analysis for SPY $700 Call:")
    print(f"  Liquidity Score: {analysis['liquidity_score']:.0f}/100")
    print(f"  Recommendation: {analysis['recommendation']}")
    print(f"  Volume Trend: {analysis['volume_trend']} ({analysis['volume_change_pct']:+.1f}%)")
    
    # Generate report
    print("\n" + tracker.generate_liquidity_report())
    
    # Save analysis
    saved = tracker.save_analysis()
    print(f"✓ Analysis saved to: {saved}")
