"""
Create visual dashboard of the SPY trading decision.
Generates an interactive HTML chart with decision metrics and trade monitor data.
"""
import json
import os
from pathlib import Path
from datetime import datetime


def load_trades_data():
    """Load trades from database and calculate statistics"""
    trades_file = Path(__file__).parent.parent / "data" / "trades.json"
    
    if not trades_file.exists():
        return None, []
    
    with open(trades_file, 'r') as f:
        data = json.load(f)
    
    trades = data.get('trades', [])
    
    # Filter open trades
    open_trades = [t for t in trades if t.get('exit') is None]
    
    # Sort by DTE (days to expiry) - most urgent first
    open_trades = sorted(open_trades, key=lambda x: x.get('expiry_dte', 999))
    
    return data.get('summary', {}), open_trades


def _generate_trades_html(expiring_trades: list, current_spy: float) -> str:
    """Generate HTML table for expiring trades"""
    if not expiring_trades:
        return '<p class="no-trades">No trades expiring in 1-2 days</p>'
    
    html = '<table class="trades-table"><thead><tr>'
    headers = ['Trade ID', 'Strike', 'DTE', 'Entry', 'Current', 'Intrinsic', 'P&L', 'Status']
    for header in headers:
        html += f'<th>{header}</th>'
    html += '</tr></thead><tbody>'
    
    total_pnl = 0
    total_contracts = 0
    
    for trade in expiring_trades:
        trade_id = trade.get('trade_id', 'N/A')
        strike = float(trade.get('strike', 0))
        dte = trade.get('expiry_dte', 0)
        entry_data = trade.get('entry', {})
        entry_price = float(entry_data.get('premium_paid', 0))  # Use premium_paid, not price
        quantity = int(entry_data.get('contracts', 1))
        
        # Calculate current option value
        current_value = calculate_option_value_bs(current_spy, strike, T=(dte/365.0 if dte > 0 else 0.01))
        intrinsic = max(current_spy - strike, 0)
        
        # Calculate P&L
        pnl_per_contract = (current_value - entry_price) * 100
        total_pnl_trade = pnl_per_contract * quantity
        pnl_percent = ((current_value - entry_price) / entry_price * 100) if entry_price > 0 else 0
        
        total_pnl += total_pnl_trade
        total_contracts += quantity
        
        # Color coding
        pnl_color = 'trade-positive' if total_pnl_trade >= 0 else 'trade-negative'
        status_emoji = '✅' if total_pnl_trade >= 0 else '⚠️'
        
        html += f'''<tr class="{pnl_color}">
            <td>{trade_id}</td>
            <td>${strike:.0f}</td>
            <td>{dte}</td>
            <td>${entry_price:.2f}</td>
            <td>${current_value:.2f}</td>
            <td>${intrinsic:.2f}</td>
            <td>${total_pnl_trade:+.2f} ({pnl_percent:+.1f}%)</td>
            <td>{status_emoji}</td>
        </tr>'''
    
    html += '</tbody></table>'
    html += f'<div class="trades-summary"><strong>Portfolio:</strong> {total_contracts} contracts, <span class="total-pnl">${total_pnl:+.2f}</span></div>'
    
    return html


def calculate_option_value_bs(S: float, K: float, T: float = 0.01) -> float:
    """Quick Black-Scholes approximation for dashboard"""
    try:
        import numpy as np
        from scipy.stats import norm
        r = 0.045
        sigma = 0.18
        
        d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        return price
    except:
        return 0


def create_dashboard():
    """Generate an interactive HTML dashboard from final_decision.json"""
    
    # Load decision data
    reports_dir = Path(__file__).parent.parent / "reports"
    decision_file = reports_dir / "final_decision.json"
    
    if not decision_file.exists():
        print(f"Error: {decision_file} not found. Run main.py first.")
        return
    
    with open(decision_file, 'r') as f:
        data = json.load(f)
    
    # Load trades data
    summary, expiring_trades = load_trades_data()
    current_spy = data.get("market_conditions", {}).get("spy_price", 689.58)
    
    # Extract key metrics
    decision = data.get("decision", "HOLD")
    score = data.get("final_score", 50)
    confidence = data.get("confidence", "UNKNOWN")
    timestamp = data.get("timestamp", "N/A")
    
    components = data.get("component_scores", {})
    momentum = components.get("momentum", 0)
    sentiment = components.get("sentiment_overall", 0)
    alignment = components.get("alignment", 0)
    event_driven = components.get("event_driven", 0)
    
    market = data.get("market_conditions", {})
    spy_price = market.get("spy_price", 0)
    rsi = market.get("rsi", 50)
    vix = market.get("vix", 15)
    trend = market.get("trend", "NEUTRAL")
    
    bullish = len(data.get("bullish_factors", []))
    bearish = len(data.get("bearish_factors", []))
    
    # Determine colors
    decision_color = {
        "BUY": "#28a745",
        "BUY SMALL": "#85c929",
        "HOLD": "#ffc107",
        "SELL SMALL": "#fd7e14",
        "SELL": "#dc3545"
    }.get(decision, "#6c757d")
    
    # Generate trades HTML
    trades_html = _generate_trades_html(expiring_trades, current_spy)
    
    # Create HTML
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
            
            .metric-unit {{
                color: #999;
                font-size: 14px;
                margin-left: 5px;
            }}
            
            .charts {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
                gap: 20px;
                margin: 20px 0;
            }}
            
            .chart-container {{
                background: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            }}
            
            .chart-container h3 {{
                color: #333;
                margin-bottom: 15px;
                font-size: 16px;
            }}
            
            .chart-wrapper {{
                position: relative;
                height: 300px;
            }}
            
            .comparison {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
                margin: 20px 0;
            }}
            
            .comparison-card {{
                background: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            }}
            
            .gauge-wrapper {{
                position: relative;
                height: 300px;
            }}
            
            .list {{
                background: white;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                margin: 20px 0;
            }}
            
            .list h3 {{
                background: #f8f9fa;
                padding: 15px 20px;
                color: #333;
                font-size: 16px;
                border-bottom: 1px solid #dee2e6;
                margin: 0;
            }}
            
            .list-item {{
                padding: 15px 20px;
                border-bottom: 1px solid #dee2e6;
                display: grid;
                grid-template-columns: 120px 80px 80px 100px 100px 100px 1fr;
                gap: 15px;
                align-items: center;
                font-size: 13px;
            }}
            
            .list-item:last-child {{
                border-bottom: none;
            }}
            
            .list-header {{
                background: #f8f9fa;
                padding: 12px 20px;
                display: grid;
                grid-template-columns: 120px 80px 80px 100px 100px 100px 1fr;
                gap: 15px;
                font-weight: 600;
                color: #666;
                font-size: 12px;
                border-bottom: 1px solid #dee2e6;
            }}
            
            .trade-positive {{
                color: #28a745;
                font-weight: 600;
            }}
            
            .trade-negative {{
                color: #dc3545;
                font-weight: 600;
            }}
            
            .trade-neutral {{
                color: #6c757d;
            }}
            
            .trades-section {{
                margin-top: 30px;
            }}
            
            .no-trades {{
                padding: 20px;
                text-align: center;
                color: #999;
                background: white;
                border-radius: 8px;
            }}
            
            .factors-list {{
                list-style: none;
            }}
            
            .factors-list li {{
                padding: 8px 0;
                color: #666;
                border-bottom: 1px solid #eee;
            }}
            
            .factors-list li:last-child {{
                border-bottom: none;
            }}
            
            .bullish {{
                color: #28a745;
                font-weight: 500;
            }}
            
            .bearish {{
                color: #dc3545;
                font-weight: 500;
            }}
            
            .footer {{
                text-align: center;
                color: white;
                margin-top: 30px;
                font-size: 12px;
            }}
            
            @media (max-width: 768px) {{
                .comparison {{
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
                <p>Generated: {timestamp}</p>
            </div>
            
            <div class="decision-box">
                <h2>{decision}</h2>
                <div class="score">{score}/100</div>
                <div class="confidence">Confidence: {confidence}</div>
            </div>
            
            <div class="metrics">
                <div class="metric-card">
                    <h3>📈 SPY Price</h3>
                    <div class="metric-value">${spy_price:.2f}</div>
                </div>
                <div class="metric-card">
                    <h3>📊 Trend</h3>
                    <div class="metric-value">{trend}</div>
                </div>
                <div class="metric-card">
                    <h3>📉 RSI</h3>
                    <div class="metric-value">{rsi:.1f}<span class="metric-unit">/100</span></div>
                </div>
                <div class="metric-card">
                    <h3>😨 VIX</h3>
                    <div class="metric-value">{vix:.1f}</div>
                </div>
            </div>
            
            <div class="charts">
                <div class="chart-container">
                    <h3>🎯 Decision Components</h3>
                    <div class="chart-wrapper">
                        <canvas id="componentsChart"></canvas>
                    </div>
                </div>
                
                <div class="chart-container">
                    <h3>💡 Score Breakdown</h3>
                    <div class="chart-wrapper">
                        <canvas id="gaugeChart"></canvas>
                    </div>
                </div>
            </div>
            
            <div class="comparison">
                <div class="comparison-card">
                    <h3>✅ Bullish Factors ({bullish})</h3>
                    <ul class="factors-list">
                        {chr(10).join(f'<li class="bullish">• {factor}</li>' for factor in data.get("bullish_factors", [])[:5])}
                    </ul>
                </div>
                
                <div class="comparison-card">
                    <h3>❌ Bearish Factors ({bearish})</h3>
                    <ul class="factors-list">
                        {chr(10).join(f'<li class="bearish">• {factor}</li>' for factor in data.get("bearish_factors", [])[:5])}
                    </ul>
                </div>
            </div>
            
            <div class="trades-section">
                <h2>📊 Open Trades - Expiring in 1-2 Days</h2>
                {trades_html}
            </div>
            
            <div class="footer">
                <p>💼 Trading System Dashboard | For educational purposes only</p>
                <p style="margin-top: 10px; font-size: 11px;">Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
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
                        data: [{momentum}, {sentiment}, {alignment}, {event_driven}],
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
    
    # Write HTML file
    output_file = reports_dir / "dashboard.html"
    with open(output_file, 'w') as f:
        f.write(html)
    
    print(f"✓ Dashboard created: {output_file}")
    print(f"  Open in browser: file://{output_file}")


if __name__ == '__main__':
    create_dashboard()
