#!/usr/bin/env python3
"""
Dashboard HTML Generator - Dynamically updates dashboard with latest analysis results
Reads JSON reports and generates interactive HTML dashboard
"""

import json
from pathlib import Path
from datetime import datetime


class DashboardUpdater:
    """Generates and updates the dashboard HTML with latest analysis results."""
    
    def __init__(self, reports_dir: str = None):
        """Initialize with reports directory path."""
        if reports_dir is None:
            reports_dir = str(Path(__file__).parent.parent / "reports")
        self.reports_dir = Path(reports_dir)
        self.dashboard_path = self.reports_dir / "dashboard.html"
    
    def load_final_decision(self):
        """Load the final decision JSON."""
        decision_file = self.reports_dir / "final_decision.json"
        if decision_file.exists():
            with open(decision_file, 'r') as f:
                return json.load(f)
        return None
    
    def load_sentiment(self):
        """Load the sentiment analysis."""
        sentiment_file = self.reports_dir / "sentiment.json"
        if sentiment_file.exists():
            with open(sentiment_file, 'r') as f:
                data = json.load(f)
                # Return overall sentiment score
                if isinstance(data, dict):
                    if "overall" in data:
                        overall = data["overall"]
                        if "blended_score" in overall:
                            return {"overall_sentiment": overall["blended_score"], "articles": data.get("top_headlines", [])}
                        elif "headline_score" in overall:
                            return {"overall_sentiment": overall["headline_score"], "articles": data.get("top_headlines", [])}
                return {"overall_sentiment": 0.5, "articles": []}
        return {"overall_sentiment": 0.5, "articles": []}
    
    def load_momentum(self):
        """Load the momentum analysis."""
        momentum_file = self.reports_dir / "momentum.json"
        if momentum_file.exists():
            with open(momentum_file, 'r') as f:
                data = json.load(f)
                # Extract what we need for the dashboard
                return {
                    "trend": data.get("trend", "NEUTRAL"),
                    "rsi": data.get("rsi", 50.0)
                }
        return {"trend": "NEUTRAL", "rsi": 50.0}
    
    def load_price_analysis(self):
        """Load the price analysis."""
        price_file = self.reports_dir / "price_analysis.json"
        if price_file.exists():
            with open(price_file, 'r') as f:
                data = json.load(f)
                # Extract the current price
                return {"current_price": data.get("current_price", "N/A")}
        return {"current_price": "N/A"}
    
    def load_trades(self):
        """Load trades from the trades.json file."""
        # Try multiple possible locations for trades.json
        possible_locations = [
            self.reports_dir / "trades.json",
            self.reports_dir.parent / "data" / "trades.json",
            Path(__file__).parent.parent / "data" / "trades.json"
        ]
        
        for trades_file in possible_locations:
            if trades_file.exists():
                with open(trades_file, 'r') as f:
                    return json.load(f)
        return {"trades": []}
    
    def load_holdings_comparison(self):
        """Load the top 5 holdings comparison data."""
        comparison_file = self.reports_dir / "top_5_holdings" / "top_5_comparison.json"
        if comparison_file.exists():
            try:
                with open(comparison_file, 'r') as f:
                    data = json.load(f)
                    # Convert results to holdings format for easier processing
                    holdings_data = {}
                    for ticker, result in data.get('results', {}).items():
                        holdings_data[ticker] = result
                    return {"holdings": holdings_data}
            except:
                pass
        return {}
    
    def load_individual_holdings_details(self):
        """Load detailed analysis for each individual holding."""
        holdings_dir = self.reports_dir / "top_5_holdings"
        tickers = ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL"]
        holdings_details = {}
        
        for ticker in tickers:
            ticker_dir = holdings_dir / ticker
            decision_file = ticker_dir / "final_decision.json"
            
            if decision_file.exists():
                try:
                    with open(decision_file, 'r') as f:
                        data = json.load(f)
                        holdings_details[ticker] = {
                            "score": data.get("final_score", 0),
                            "decision": data.get("decision", "HOLD"),
                            "confidence": data.get("confidence", "LOW"),
                            "trend": data.get("market_conditions", {}).get("trend", "NEUTRAL"),
                            "rsi": data.get("market_conditions", {}).get("rsi", 50),
                            "price": data.get("market_conditions", {}).get("spy_price", 0),
                            "components": data.get("component_scores", {}),
                            "entry": data.get("entry_strategy", {}).get("recommended_entry", 0),
                            "target": data.get("risk_reward", {}).get("take_profit_target", 0),
                            "stop": data.get("risk_reward", {}).get("stop_loss_level", 0),
                        }
                except:
                    pass
        
        return holdings_details
    

    def _get_decision_color(self, decision: str) -> str:
        """Get color for decision type."""
        decision_colors = {
            "BUY": "#85c929",          # Green
            "BUY SMALL": "#85c929",    # Green
            "BUY_SMALL": "#85c929",    # Green (alternate format)
            "SELL": "#e74c3c",         # Red
            "SELL_COVERED": "#e74c3c", # Red
            "SELL COVERED": "#e74c3c", # Red (alternate format)
            "HOLD": "#f39c12",         # Orange
            "SELL_PUT": "#3498db",     # Blue
            "SELL PUT": "#3498db"      # Blue (alternate format)
        }
        return decision_colors.get(decision, "#95a5a6")
    
    def _generate_holdings_comparison_section(self, holdings_data: dict) -> str:
        """Generate holdings comparison table."""
        if not holdings_data or not holdings_data.get("holdings"):
            return ""
        
        holdings = holdings_data.get("holdings", {})
        
        # Build table rows
        rows_html = ""
        for ticker, data in holdings.items():
            decision = data.get("decision", "HOLD")
            score = data.get("score", 0)
            weight = data.get("weight", 0)
            
            # Try to load sentiment from the holding's sentiment.json
            sentiment = 0.5
            try:
                sentiment_file = self.reports_dir / "top_5_holdings" / ticker / "sentiment.json"
                if sentiment_file.exists():
                    with open(sentiment_file, 'r') as f:
                        sent_data = json.load(f)
                        overall = sent_data.get('overall', {})
                        if "blended_score" in overall:
                            sentiment = overall["blended_score"]
                        elif "headline_score" in overall:
                            sentiment = overall["headline_score"]
            except:
                pass
            
            decision_color = self._get_decision_color(decision)
            sentiment_label = "Bullish" if sentiment > 0.55 else "Bearish" if sentiment < 0.45 else "Neutral"
            
            rows_html += f"""
            <tr>
                <td><strong>{ticker}</strong></td>
                <td><span style="background: {decision_color}; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;">{decision}</span></td>
                <td>{score:.1f}/100</td>
                <td><span title="{sentiment:.2f}/1.0">{sentiment_label}</span></td>
                <td>{weight:.2f}%</td>
            </tr>"""
        
        return f"""
            <div class="analysis-section">
                <h3>🏢 Top 5 Holdings Comparison</h3>
                <table class="holdings-table">
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Decision</th>
                            <th>Score</th>
                            <th title="News sentiment analysis - what people are saying about the stock">📰 Sentiment (News)</th>
                            <th>SPY Weight</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
                <p style="font-size: 12px; color: #666; margin-top: 10px;">
                  <strong>📰 Sentiment</strong> = News headline analysis<br/>
                  <strong>Weight</strong> = % of SPY index composed by this holding
                </p>
            </div>"""
    
    def _generate_detailed_holdings_section(self, holdings_details: dict) -> str:
        """Generate detailed individual holdings analysis section."""
        if not holdings_details:
            return ""
        
        rows_html = ""
        for ticker in ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL"]:
            if ticker not in holdings_details:
                continue
            
            data = holdings_details[ticker]
            score = data.get("score", 0)
            decision = data.get("decision", "HOLD")
            confidence = data.get("confidence", "LOW")
            trend = data.get("trend", "NEUTRAL")
            rsi = data.get("rsi", 50)
            price = data.get("price", 0)
            entry = data.get("entry", 0)
            target = data.get("target", 0)
            stop = data.get("stop", 0)
            
            decision_color = self._get_decision_color(decision)
            trend_color = "#85c929" if trend == "BULLISH" else "#e74c3c" if trend == "BEARISH" else "#f39c12"
            
            # Calculate potential gain/loss
            if entry > 0:
                gain_pct = ((target - entry) / entry * 100) if target > 0 else 0
                loss_pct = ((entry - stop) / entry * 100) if stop > 0 else 0
            else:
                gain_pct = 0
                loss_pct = 0
            
            rows_html += f"""
            <tr>
                <td><strong>{ticker}</strong></td>
                <td><span style="background: {decision_color}; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 12px;">{decision}</span></td>
                <td>{score:.1f}</td>
                <td>{confidence}</td>
                <td><span style="color: {trend_color}; font-weight: bold;">{trend}</span></td>
                <td>{rsi:.1f}</td>
                <td>${price:.2f}</td>
                <td>${entry:.2f}</td>
                <td>${target:.2f} <span style="color: green; font-size: 11px;">(+{gain_pct:.1f}%)</span></td>
                <td>${stop:.2f} <span style="color: red; font-size: 11px;">(-{loss_pct:.1f}%)</span></td>
            </tr>"""
        
        return f"""
            <div class="analysis-section" style="overflow-x: auto;">
                <h3>📊 Individual Holdings Detailed Analysis</h3>
                <table class="holdings-table" style="font-size: 13px;">
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Decision</th>
                            <th>Score</th>
                            <th>Confidence</th>
                            <th title="Price momentum trend (RSI, EMA comparison - technical analysis)">📈 Trend (Price)</th>
                            <th>RSI</th>
                            <th>Current Price</th>
                            <th>Entry</th>
                            <th>Target</th>
                            <th>Stop Loss</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
                <p style="font-size: 12px; color: #666; margin-top: 10px;">
                  <strong>📈 Trend (Price)</strong> = Price momentum based on RSI, EMA, VWAP<br/>
                  <strong>💡 Note:</strong> Bullish sentiment + Bearish trend = Bullish Divergence (potential undervaluation signal)
                </p>
            </div>"""
    
    def _generate_sentiment_section(self, sentiment: dict) -> str:
        """Generate sentiment analysis section."""
        overall = sentiment.get("overall_sentiment", 0.5)
        articles = sentiment.get("articles", [])
        
        sentiment_color = "#85c929" if overall > 0.55 else "#e74c3c" if overall < 0.45 else "#f39c12"
        sentiment_label = "BULLISH" if overall > 0.55 else "BEARISH" if overall < 0.45 else "NEUTRAL"
        
        articles_html = ""
        for article in articles[:3]:  # Top 3 articles
            # Handle both dict and string formats for articles
            if isinstance(article, dict):
                headline = article.get('headline', 'Unknown')
                source = article.get('source', 'Unknown')
                sentiment_val = article.get('sentiment', 'Neutral')
            else:
                # If it's just a string (headline)
                headline = article
                source = 'News'
                sentiment_val = 'Neutral'
            
            articles_html += f"""
                    <div style="margin: 10px 0; padding: 10px; background: #f8f9fa; border-left: 3px solid {sentiment_color}; border-radius: 4px;">
                        <strong>{headline}</strong><br/>
                        <small style="color: #666;">{source} - {sentiment_val}</small>
                    </div>"""
        
        return f"""
            <div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin: 20px 0;">
                <h3 style="margin-bottom: 15px;">📰 Sentiment Analysis</h3>
                <div style="display: flex; align-items: center; margin-bottom: 15px;">
                    <div style="font-size: 28px; font-weight: bold; color: {sentiment_color}; margin-right: 20px;">{sentiment_label}</div>
                    <div style="color: #666;">Score: {overall:.2f}/1.0</div>
                </div>
                {articles_html}
            </div>"""
    
    def _generate_components_chart_data(self, final_decision: dict) -> str:
        """Generate component scores for chart."""
        component_scores = final_decision.get("component_scores", {})
        
        # Map the actual keys from final_decision.json
        momentum = component_scores.get("momentum", 0.5)
        sentiment = component_scores.get("sentiment_overall", component_scores.get("sentiment", 0.5))
        alignment = component_scores.get("alignment", 0.5)
        events = component_scores.get("event_driven", component_scores.get("events", 0.5))
        
        # Ensure all values are normalized to 0-1 range
        momentum = min(max(float(momentum), 0), 1)
        sentiment = min(max(float(sentiment), 0), 1)
        alignment = min(max(float(alignment), 0), 1)
        events = min(max(float(events), 0), 1)
        
        return f"[{momentum:.2f}, {sentiment:.2f}, {alignment:.2f}, {events:.2f}]"
    
    def _generate_trade_rows(self, trades: dict) -> str:
        """Generate trade table rows."""
        trades_list = trades.get("trades", [])
        rows = ""
        
        for trade in trades_list:
            trade_id = trade.get("trade_id", "N/A")
            strike = trade.get("strike", "N/A")
            
            # Handle nested entry/exit structure
            entry = trade.get("entry", {})
            exit_data = trade.get("exit", {})
            
            qty = entry.get("contracts", trade.get("quantity", 0))
            
            # Get entry premium - try premium_paid first, then price
            if "premium_paid" in entry:
                entry_premium = entry.get("premium_paid", 0)
            else:
                entry_premium = entry.get("price", entry.get("entry_premium", 0))
            
            # Get current/exit premium - try premium_sold first, then price
            if "premium_sold" in exit_data:
                current_premium = exit_data.get("premium_sold", entry_premium)
            else:
                current_premium = exit_data.get("price", entry_premium)
            
            # Check if trade is closed (has exit data)
            if exit_data and exit_data.get("profit") is not None:
                pnl = exit_data.get("profit", 0)
                pnl_pct = exit_data.get("profit_pct", 0)
                status = "✅" if pnl > 0 else "❌"
                row_class = "trade-positive" if pnl > 0 else "trade-negative"
                # For closed trades, use exit premium
                if "premium_sold" in exit_data:
                    exit_premium = exit_data.get("premium_sold", current_premium)
                else:
                    exit_premium = exit_data.get("price", current_premium)
            else:
                exit_premium = current_premium
                pnl = (current_premium - entry_premium) * qty * 100 if entry_premium else 0
                pnl_pct = ((current_premium - entry_premium) / entry_premium * 100) if entry_premium else 0
                status = "📊"
                row_class = "trade-positive" if pnl > 0 else "trade-negative"
            
            rows += f"""<tr class="{row_class}">
            <td>{trade_id}</td>
            <td>${strike}</td>
            <td>{qty}</td>
            <td>${entry_premium:.2f}</td>
            <td>${current_premium:.2f}</td>
            <td>${exit_premium:.2f}</td>
            <td>${pnl:+.2f} ({pnl_pct:+.1f}%)</td>
            <td>{status}</td>
        </tr>"""
        
        return rows
    
    def _calculate_portfolio_stats(self, trades: dict) -> tuple:
        """Calculate total contracts and P&L."""
        trades_list = trades.get("trades", [])
        total_contracts = 0
        total_pnl = 0
        
        for trade in trades_list:
            # Handle nested entry/exit structure
            entry = trade.get("entry", {})
            exit_data = trade.get("exit", {})
            
            qty = entry.get("contracts", trade.get("quantity", 0))
            total_contracts += qty
            
            # If trade has exit data with profit, use that
            if exit_data and "profit" in exit_data:
                total_pnl += exit_data.get("profit", 0)
            else:
                # Otherwise calculate from current price
                # Try premium_paid first, then price
                if "premium_paid" in entry:
                    entry_price = entry.get("premium_paid", 0)
                else:
                    entry_price = entry.get("price", 0)
                
                # Try premium_sold first, then price
                if "premium_sold" in exit_data:
                    current_price = exit_data.get("premium_sold", entry_price)
                else:
                    current_price = exit_data.get("price", entry_price)
                
                if entry_price:
                    pnl = (current_price - entry_price) * qty * 100
                    total_pnl += pnl
        
        return total_contracts, total_pnl
    
    def generate_html(self) -> str:
        """Generate complete dashboard HTML."""
        
        # Load all data
        final_decision = self.load_final_decision()
        sentiment = self.load_sentiment()
        momentum = self.load_momentum()
        price_analysis = self.load_price_analysis()
        trades = self.load_trades()
        holdings_comparison = self.load_holdings_comparison()
        holdings_details = self.load_individual_holdings_details()
        
        if not final_decision:
            return self._generate_error_html()
        
        # Extract key data
        decision = final_decision.get("decision", "HOLD")
        score = final_decision.get("final_score", 50)
        confidence = final_decision.get("confidence", "MEDIUM")
        explanation = final_decision.get("recommendation", {}).get("explanation", [])
        
        decision_color = self._get_decision_color(decision)
        components_data = self._generate_components_chart_data(final_decision)
        trade_rows = self._generate_trade_rows(trades)
        total_contracts, total_pnl = self._calculate_portfolio_stats(trades)
        
        # Current timestamp
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Generate sentiment section
        sentiment_section = self._generate_sentiment_section(sentiment)
        
        # Generate holdings comparison section
        holdings_section = self._generate_holdings_comparison_section(holdings_comparison)
        
        # Generate detailed holdings section
        detailed_holdings_section = self._generate_detailed_holdings_section(holdings_details)
        
        # Build explanation HTML before f-string
        explanation_html = ""
        for point in explanation:
            explanation_html += f"\n                        <li>{point}</li>"
        
        html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SPY Trading Decision Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            
            .container {{
                max-width: 1400px;
                margin: 0 auto;
            }}
            
            .header {{
                background: white;
                padding: 30px;
                border-radius: 10px;
                margin-bottom: 20px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }}
            
            .header h1 {{
                font-size: 24px;
                color: #333;
                margin-bottom: 10px;
            }}
            
            .header p {{
                color: #666;
                font-size: 14px;
            }}
            
            .decision-box {{
                background: {decision_color};
                color: white;
                padding: 30px;
                border-radius: 10px;
                margin: 20px 0;
                text-align: center;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
            }}
            
            .decision-box h2 {{
                font-size: 32px;
                font-weight: bold;
                margin-bottom: 10px;
            }}
            
            .decision-box .score {{
                font-size: 48px;
                font-weight: bold;
                margin: 15px 0;
            }}
            
            .decision-box .confidence {{
                font-size: 18px;
                opacity: 0.9;
            }}
            
            .metrics {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 15px;
                margin: 20px 0;
            }}
            
            .metric-card {{
                background: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            }}
            
            .metric-card h3 {{
                color: #666;
                font-size: 12px;
                text-transform: uppercase;
                margin-bottom: 10px;
                font-weight: 600;
            }}
            
            .metric-value {{
                font-size: 28px;
                font-weight: bold;
                color: #333;
            }}
            
            .analysis-section {{
                background: white;
                padding: 30px;
                border-radius: 10px;
                margin: 20px 0;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            }}
            
            .analysis-section h3 {{
                margin-bottom: 20px;
                color: #333;
                font-size: 18px;
            }}
            
            .chart-container {{
                position: relative;
                height: 300px;
                margin: 20px 0;
            }}
            
            .explanation {{
                background: #f8f9fa;
                padding: 15px;
                border-left: 4px solid {decision_color};
                border-radius: 4px;
                margin: 15px 0;
            }}
            
            .explanation li {{
                margin: 8px 0;
                color: #555;
            }}
            
            .trades-section {{
                margin-top: 30px;
            }}
            
            .trades-table {{
                width: 100%;
                border-collapse: collapse;
                margin: 15px 0;
            }}
            
            .trades-table thead {{
                background: #f8f9fa;
            }}
            
            .trades-table th {{
                padding: 12px;
                text-align: left;
                font-weight: 600;
                color: #333;
                border-bottom: 2px solid #ddd;
            }}
            
            .trades-table td {{
                padding: 12px;
                border-bottom: 1px solid #eee;
            }}
            
            .trade-positive {{
                background: #f0f9f4;
            }}
            
            .trade-negative {{
                background: #fef2f2;
            }}
            
            .trades-summary {{
                padding: 15px;
                background: #f8f9fa;
                border-radius: 4px;
                margin-top: 15px;
                text-align: right;
            }}
            
            .total-pnl {{
                font-weight: bold;
                color: {decision_color};
                font-size: 18px;
            }}
            
            .holdings-table {{
                width: 100%;
                border-collapse: collapse;
                margin: 15px 0;
            }}
            
            .holdings-table thead {{
                background: #f8f9fa;
            }}
            
            .holdings-table th {{
                padding: 12px;
                text-align: left;
                font-weight: 600;
                color: #333;
                border-bottom: 2px solid #ddd;
            }}
            
            .holdings-table td {{
                padding: 12px;
                border-bottom: 1px solid #eee;
            }}
            
            .holdings-table tbody tr:hover {{
                background: #f8f9fa;
            }}
            
            .footer {{
                text-align: center;
                color: white;
                margin-top: 40px;
                padding: 20px;
            }}
            
            @media (max-width: 768px) {{
                .metrics {{
                    grid-template-columns: 1fr;
                }}
                
                .decision-box h2 {{
                    font-size: 24px;
                }}
                
                .decision-box .score {{
                    font-size: 36px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📊 SPY OPTIONS TRADING DECISION</h1>
                <p>Local Analysis System | Real-time Market Data</p>
            </div>
            
            <div class="decision-box">
                <h2>{decision}</h2>
                <div class="score">{score}/100</div>
                <div class="confidence">Confidence: {confidence}</div>
            </div>
            
            <div class="metrics">
                <div class="metric-card">
                    <h3>Current Price</h3>
                    <div class="metric-value">${price_analysis.get('current_price', 'N/A')}</div>
                </div>
                <div class="metric-card">
                    <h3>Trend</h3>
                    <div class="metric-value">{momentum.get('trend', 'N/A')}</div>
                </div>
                <div class="metric-card">
                    <h3>RSI</h3>
                    <div class="metric-value">{momentum.get('rsi', 'N/A'):.1f}</div>
                </div>
                <div class="metric-card">
                    <h3>Sentiment</h3>
                    <div class="metric-value">{sentiment.get('overall_sentiment', 0.5):.2f}/1.0</div>
                </div>
            </div>
            
            <div class="analysis-section">
                <h3>🎯 Decision Rationale</h3>
                <div class="explanation">
                    <ul>{explanation_html}
                    </ul>
                </div>
            </div>
            
            <div class="analysis-section">
                <h3>📈 Analysis Components</h3>
                <div class="chart-container">
                    <canvas id="componentsChart"></canvas>
                </div>
            </div>
            
            <div class="analysis-section">
                <h3>⚡ Score Distribution</h3>
                <div class="chart-container">
                    <canvas id="gaugeChart"></canvas>
                </div>
            </div>
            
            {holdings_section}
            
            {detailed_holdings_section}
            
            <div class="analysis-section trades-section">
                <h3>💼 Active Trades</h3>
                <table class="trades-table">
                    <thead>
                        <tr>
                            <th>Trade ID</th>
                            <th>Strike</th>
                            <th>Qty</th>
                            <th>Entry Premium</th>
                            <th>Current</th>
                            <th>Exit</th>
                            <th>P&L</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {trade_rows}
                    </tbody>
                </table>
                <div class="trades-summary"><strong>Portfolio:</strong> {total_contracts} contracts, <span class="total-pnl">${total_pnl:+.2f}</span></div>
            </div>
            
            <div class="footer">
                <p>💼 Trading System Dashboard | For educational purposes only</p>
                <p style="margin-top: 10px; font-size: 11px;">Last updated: {now}</p>
            </div>
        </div>
        
        <script>
            // Components Chart
            const ctx1 = document.getElementById('componentsChart').getContext('2d');
            new Chart(ctx1, {{
                type: 'bar',
                data: {{
                    labels: ['Momentum', 'Sentiment', 'Alignment', 'Event-Driven'],
                    datasets: [{{
                        label: 'Score',
                        data: {components_data},
                        backgroundColor: [
                            'rgba(102, 126, 234, 0.8)',
                            'rgba(118, 75, 162, 0.8)',
                            'rgba(40, 167, 69, 0.8)',
                            'rgba(255, 193, 7, 0.8)'
                        ],
                        borderColor: [
                            'rgb(102, 126, 234)',
                            'rgb(118, 75, 162)',
                            'rgb(40, 167, 69)',
                            'rgb(255, 193, 7)'
                        ],
                        borderWidth: 2,
                        borderRadius: 5
                    }}]
                }},
                options: {{
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{
                            display: false
                        }}
                    }},
                    scales: {{
                        x: {{
                            beginAtZero: true,
                            max: 1.0,
                            ticks: {{
                                callback: function(value) {{
                                    return value.toFixed(2);
                                }}
                            }}
                        }}
                    }}
                }}
            }});
            
            // Gauge Chart (Pie)
            const ctx2 = document.getElementById('gaugeChart').getContext('2d');
            new Chart(ctx2, {{
                type: 'doughnut',
                data: {{
                    labels: ['Score', 'Remaining'],
                    datasets: [{{
                        data: [{score}, {100 - score}],
                        backgroundColor: [
                            '{decision_color}',
                            'rgba(200, 200, 200, 0.2)'
                        ],
                        borderColor: [
                            '{decision_color}',
                            'rgba(200, 200, 200, 0.5)'
                        ],
                        borderWidth: 2
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{
                            display: false
                        }},
                        tooltip: {{
                            callbacks: {{
                                label: function(context) {{
                                    return context.label + ': ' + context.parsed + '/100';
                                }}
                            }}
                        }}
                    }}
                }}
            }});
        </script>
    </body>
    </html>
    """
        
        return html
    
    def _generate_error_html(self) -> str:
        """Generate error page if data is not available."""
        return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SPY Trading Dashboard - No Data</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
                text-align: center;
                max-width: 500px;
            }
            h1 {
                color: #333;
                margin-bottom: 20px;
            }
            p {
                color: #666;
                line-height: 1.6;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📊 Dashboard - Waiting for Data</h1>
            <p>No analysis data available yet.</p>
            <p>Run the decision engine to generate reports and populate the dashboard.</p>
        </div>
    </body>
    </html>
        """
    
    def update(self) -> bool:
        """Generate and save updated dashboard HTML."""
        try:
            html = self.generate_html()
            with open(self.dashboard_path, 'w') as f:
                f.write(html)
            print(f"✓ Dashboard updated: {self.dashboard_path}")
            return True
        except Exception as e:
            print(f"❌ Error updating dashboard: {e}")
            return False
