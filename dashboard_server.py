#!/usr/bin/env python3
"""
Dashboard Web Server - Serves the SPY trading dashboard with live analysis updates
Allows running analysis and updating dashboard in real-time
Integrated with earnings analysis dashboard
"""

import json
import subprocess
import sys
from pathlib import Path
from flask import Flask, render_template, render_template_string, jsonify
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px

# Add earnings_tracker to path
sys.path.insert(0, str(Path(__file__).parent / "earnings_tracker"))
from earnings_analyzer import EarningsAnalyzer

app = Flask(__name__, 
            template_folder=str(Path(__file__).parent / "spy_decision_engine" / "templates"))

# Get reports directory
REPORTS_DIR = Path(__file__).parent / "spy_decision_engine" / "reports"
DASHBOARD_HTML = REPORTS_DIR / "dashboard.html"
MAIN_SCRIPT = Path(__file__).parent / "spy_decision_engine" / "main.py"

# Initialize earnings analyzer
analyzer = EarningsAnalyzer()


def get_dashboard_html():
    """Load and return the current dashboard HTML."""
    if DASHBOARD_HTML.exists():
        with open(DASHBOARD_HTML, 'r') as f:
            return f.read()
    return "<h1>Dashboard not found. Run analysis first.</h1>"


def run_analysis():
    """Execute the main analysis script."""
    try:
        print(f"\n🚀 Running analysis at {datetime.now().strftime('%H:%M:%S')}...")
        result = subprocess.run(
            [sys.executable, str(MAIN_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            print("✅ Analysis completed successfully")
            return True, "Analysis completed successfully"
        else:
            error_msg = result.stderr or "Unknown error"
            print(f"❌ Analysis failed: {error_msg}")
            return False, f"Analysis failed: {error_msg}"
    
    except subprocess.TimeoutExpired:
        return False, "Analysis timed out (took more than 5 minutes)"
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error running analysis: {error_msg}")
        return False, f"Error: {error_msg}"


@app.route('/')
def dashboard():
    """Serve the main dashboard."""
    html = get_dashboard_html()
    
    # Inject update button and script into the HTML
    update_button_html = """
    <div style="position: fixed; top: 20px; right: 20px; z-index: 1000;">
        <button id="updateBtn" onclick="updateAnalysis()" 
                style="background: #4CAF50; color: white; padding: 12px 24px; 
                       border: none; border-radius: 4px; cursor: pointer; 
                       font-weight: bold; font-size: 14px;">
            🔄 Update Analysis
        </button>
        <div id="statusMsg" style="margin-top: 10px; padding: 10px; 
                                    text-align: center; font-weight: bold;
                                    display: none;"></div>
    </div>
    
    <script>
        function updateAnalysis() {
            const btn = document.getElementById('updateBtn');
            const status = document.getElementById('statusMsg');
            
            btn.disabled = true;
            btn.style.opacity = '0.6';
            btn.style.cursor = 'not-allowed';
            
            status.style.display = 'block';
            status.textContent = '⏳ Running analysis...';
            status.style.color = '#f39c12';
            
            fetch('/api/run-analysis')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        status.textContent = '✅ Analysis complete! Reloading...';
                        status.style.color = '#27ae60';
                        setTimeout(() => location.reload(), 1500);
                    } else {
                        status.textContent = '❌ ' + data.message;
                        status.style.color = '#e74c3c';
                        btn.disabled = false;
                        btn.style.opacity = '1';
                        btn.style.cursor = 'pointer';
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    status.textContent = '❌ Connection error: ' + error;
                    status.style.color = '#e74c3c';
                    btn.disabled = false;
                    btn.style.opacity = '1';
                    btn.style.cursor = 'pointer';
                });
        }
    </script>
    """
    
    # Insert the button before the closing body tag
    html = html.replace('</body>', update_button_html + '</body>')
    
    return html


@app.route('/api/run-analysis', methods=['GET', 'POST'])
def api_run_analysis():
    """API endpoint to run analysis and update dashboard."""
    success, message = run_analysis()
    
    return jsonify({
        'success': success,
        'message': message,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/status')
def api_status():
    """Check if dashboard is ready."""
    if DASHBOARD_HTML.exists():
        with open(REPORTS_DIR / "final_decision.json") as f:
            final = json.load(f)
            return jsonify({
                'ready': True,
                'score': final.get('final_score'),
                'decision': final.get('decision'),
                'timestamp': final.get('timestamp')
            })
    return jsonify({'ready': False})


# ============================================================================
# EARNINGS ANALYSIS ENDPOINTS
# ============================================================================

@app.route('/tickers')
def earnings_dashboard():
    """Serve the earnings analysis dashboard."""
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Earnings Analysis Dashboard</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
            .container { max-width: 1400px; margin: 0 auto; }
            .header { text-align: center; margin-bottom: 30px; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            .header h1 { color: #333; margin: 0; font-size: 2.5em; }
            .header p { color: #666; margin: 10px 0 0 0; font-size: 1.1em; }
            .controls { display: flex; justify-content: center; gap: 15px; margin-top: 20px; flex-wrap: wrap; }
            .btn { padding: 12px 24px; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 14px; transition: all 0.3s ease; }
            .btn-primary { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
            .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 6px 12px rgba(102, 126, 234, 0.4); }
            .btn:disabled { opacity: 0.6; cursor: not-allowed; }
            .status { padding: 12px 20px; border-radius: 6px; font-weight: 600; margin-top: 10px; display: none; }
            .status.success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .status.loading { background: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
            .status.error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
            .charts-container { display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 20px; margin-top: 20px; }
            .chart { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); overflow: hidden; }
            .chart.full { grid-column: 1 / -1; }
            .chart-title { font-weight: 600; color: #333; margin-bottom: 15px; font-size: 1.1em; }
            .stocks-highlight { background: white; padding: 20px; border-radius: 12px; margin-top: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            .stocks-highlight h3 { color: #667eea; margin-top: 0; }
            .stocks-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
            .stock-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px; border-radius: 8px; }
            .stock-card .ticker { font-weight: 700; font-size: 1.3em; }
            .stock-card .company { font-size: 0.9em; opacity: 0.9; }
            .stock-card .earnings { font-size: 0.85em; margin-top: 8px; opacity: 0.8; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📊 Earnings Analysis Dashboard</h1>
                <p>Real-time sentiment and confidence analysis for tracked stocks</p>
                <div class="controls">
                    <button class="btn btn-primary" id="updateBtn" onclick="updateDashboard()">🔄 Update Analysis</button>
                </div>
                <div id="status" class="status"></div>
            </div>
            
            <div class="stocks-highlight">
                <h3>⭐ Your Favorites - META & AAPL</h3>
                <p style="color: #666;">Detailed tracking for your top stocks with comprehensive analysis</p>
                <div class="stocks-list" id="favoritesList">
                    <div class="stock-card">
                        <div class="ticker">META</div>
                        <div class="company">Meta Platforms</div>
                        <div class="earnings">Earnings: 2026-02-04</div>
                    </div>
                    <div class="stock-card">
                        <div class="ticker">AAPL</div>
                        <div class="company">Apple</div>
                        <div class="earnings">Earnings: 2026-02-03</div>
                    </div>
                </div>
            </div>
            
            <div class="charts-container">
                <div class="chart full">
                    <div class="chart-title">📈 Stock Confidence Scores</div>
                    <div id="summary"></div>
                </div>
                <div class="chart">
                    <div class="chart-title">🎯 3D: Confidence vs Sentiment</div>
                    <div id="3d-confidence"></div>
                </div>
                <div class="chart">
                    <div class="chart-title">📊 Component Scores</div>
                    <div id="component-scores"></div>
                </div>
                <div class="chart full">
                    <div class="chart-title">🔄 Confidence vs Sentiment Analysis</div>
                    <div id="confidence-vs-sentiment"></div>
                </div>
                <div class="chart">
                    <div class="chart-title">😊 Sentiment Distribution</div>
                    <div id="sentiment-distribution"></div>
                </div>
                <div class="chart">
                    <div class="chart-title">📅 Earnings Timeline</div>
                    <div id="earnings-calendar"></div>
                </div>
            </div>
        </div>
        
        <script>
            function loadCharts() {
                document.getElementById('status').style.display = 'none';
                Promise.all([
                    fetch('/tickers/api/summary-metrics').then(r => r.json()),
                    fetch('/tickers/api/3d-confidence-chart').then(r => r.json()),
                    fetch('/tickers/api/component-scores-3d').then(r => r.json()),
                    fetch('/tickers/api/confidence-vs-sentiment').then(r => r.json()),
                    fetch('/tickers/api/sentiment-distribution').then(r => r.json()),
                    fetch('/tickers/api/earnings-calendar').then(r => r.json())
                ]).then(([summary, conf3d, scores, confvssent, sentiment, earnings]) => {
                    if (summary && summary.data) Plotly.newPlot('summary', summary.data, summary.layout, {responsive: true});
                    if (conf3d && conf3d.data) Plotly.newPlot('3d-confidence', conf3d.data, conf3d.layout, {responsive: true});
                    if (scores && scores.data) Plotly.newPlot('component-scores', scores.data, scores.layout, {responsive: true});
                    if (confvssent && confvssent.data) Plotly.newPlot('confidence-vs-sentiment', confvssent.data, confvssent.layout, {responsive: true});
                    if (sentiment && sentiment.data) Plotly.newPlot('sentiment-distribution', sentiment.data, sentiment.layout, {responsive: true});
                    if (earnings && earnings.data) Plotly.newPlot('earnings-calendar', earnings.data, earnings.layout, {responsive: true});
                }).catch(e => {
                    console.error('Error loading charts:', e);
                    showStatus('Error loading charts. Please try again.', 'error');
                });
            }
            
            function updateDashboard() {
                const btn = document.getElementById('updateBtn');
                const status = document.getElementById('status');
                
                btn.disabled = true;
                showStatus('🔄 Updating earnings analysis...', 'loading');
                
                fetch('/tickers/api/refresh')
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            showStatus('✅ Analysis updated! Refreshing charts...', 'success');
                            setTimeout(() => {
                                loadCharts();
                                btn.disabled = false;
                            }, 1000);
                        } else {
                            showStatus('❌ Update failed: ' + data.message, 'error');
                            btn.disabled = false;
                        }
                    })
                    .catch(e => {
                        showStatus('❌ Error: ' + e.message, 'error');
                        btn.disabled = false;
                    });
            }
            
            function showStatus(message, type) {
                const status = document.getElementById('status');
                status.textContent = message;
                status.className = 'status ' + type;
                status.style.display = 'block';
                if (type === 'success') {
                    setTimeout(() => { status.style.display = 'none'; }, 3000);
                }
            }
            
            // Load charts on page load
            loadCharts();
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template)


@app.route('/tickers/api/refresh', methods=['GET', 'POST'])
def api_refresh_earnings():
    """Refresh and reload earnings analysis."""
    try:
        # This endpoint just triggers a reload of the analysis
        # The analysis is computed fresh each time the metrics are requested
        return jsonify({
            'success': True,
            'message': 'Earnings analysis updated',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/tickers/api/summary-metrics')
def api_summary_metrics():
    """Get summary metrics for all stocks."""
    analysis = analyzer.analyze_all_stocks()
    stocks = analysis.get("stocks", [])
    
    # Create summary table data
    summary_data = []
    for stock in stocks:
        summary_data.append({
            'ticker': stock['ticker'],
            'confidence': round(stock['confidence_score'], 1),
            'sentiment': stock['sentiment_analysis'].get('sentiment', 'neutral').upper(),
            'sentiment_score': round(stock['sentiment_analysis'].get('score', 0), 3),
            'price_trend': stock.get('price_trend', 'neutral')
        })
    
    # Create a simple bar chart showing confidence and sentiment
    tickers = [s['ticker'] for s in summary_data]
    confidences = [s['confidence'] for s in summary_data]
    
    fig = go.Figure()
    fig.add_trace(go.Bar(name='Confidence %', x=tickers, y=confidences, marker_color='steelblue'))
    fig.update_layout(
        title='Stock Confidence Scores',
        xaxis_title='Ticker',
        yaxis_title='Confidence %',
        height=400
    )
    
    return jsonify({
        'data': json.loads(fig.to_json())['data'],
        'layout': json.loads(fig.to_json())['layout'],
        'summary': summary_data
    })


@app.route('/tickers/api/3d-confidence-chart')
def api_3d_confidence():
    """Generate 3D scatter chart."""
    analysis = analyzer.analyze_all_stocks()
    stocks = analysis.get("stocks", [])
    
    tickers = [s["ticker"] for s in stocks]
    confidences = [s["confidence_score"] for s in stocks]
    sentiments = [s["sentiment_analysis"].get("score", 0) for s in stocks]
    
    fig = go.Figure(data=[go.Scatter3d(
        x=tickers, y=confidences, z=sentiments,
        mode='markers+text', text=tickers,
        marker=dict(size=8, color=sentiments, colorscale='RdBu', showscale=True),
        textposition='top center'
    )])
    fig.update_layout(title='3D: Confidence vs Sentiment', height=600)
    
    return jsonify(json.loads(fig.to_json()))


@app.route('/tickers/api/component-scores-3d')
def api_component_scores():
    """Generate component scores chart."""
    analysis = analyzer.analyze_all_stocks()
    stocks = analysis.get("stocks", [])
    
    components = ['technical', 'sentiment', 'earnings', 'volatility', 'momentum', 'liquidity', 'macro']
    
    fig = go.Figure()
    for stock in stocks:
        scores = stock.get('component_scores', {})
        values = [scores.get(c, 0) for c in components]
        fig.add_trace(go.Bar(name=stock['ticker'], x=components, y=values))
    
    fig.update_layout(
        title='Component Analysis Scores',
        barmode='group',
        xaxis_title='Components',
        yaxis_title='Score',
        height=500
    )
    
    return jsonify(json.loads(fig.to_json()))


@app.route('/tickers/api/confidence-vs-sentiment')
def api_confidence_vs_sentiment():
    """Generate confidence vs sentiment chart."""
    analysis = analyzer.analyze_all_stocks()
    stocks = analysis.get("stocks", [])
    
    tickers = [s["ticker"] for s in stocks]
    confidences = [s["confidence_score"] for s in stocks]
    sentiments = [s["sentiment_analysis"].get("score", 0) * 100 for s in stocks]
    
    fig = go.Figure(data=[go.Scatter(
        x=sentiments, y=confidences,
        mode='markers+text', text=tickers,
        marker=dict(size=12, color=confidences, colorscale='Viridis', showscale=True),
        textposition='top center'
    )])
    fig.update_layout(
        title='Confidence vs Sentiment Analysis',
        xaxis_title='Sentiment Score',
        yaxis_title='Confidence %',
        height=500
    )
    
    return jsonify(json.loads(fig.to_json()))


@app.route('/tickers/api/sentiment-distribution')
def api_sentiment_distribution():
    """Generate sentiment distribution pie chart."""
    analysis = analyzer.analyze_all_stocks()
    stocks = analysis.get("stocks", [])
    
    sentiments = {}
    for stock in stocks:
        sentiment = stock["sentiment_analysis"].get("sentiment", "neutral").upper()
        sentiments[sentiment] = sentiments.get(sentiment, 0) + 1
    
    fig = go.Figure(data=[go.Pie(
        labels=list(sentiments.keys()),
        values=list(sentiments.values()),
        hole=0.3
    )])
    fig.update_layout(title='Sentiment Distribution Across Stocks', height=500)
    
    return jsonify(json.loads(fig.to_json()))


@app.route('/tickers/api/earnings-calendar')
def api_earnings_calendar():
    """Generate earnings calendar."""
    analysis = analyzer.analyze_all_stocks()
    stocks = analysis.get("stocks", [])
    
    tickers = [s["ticker"] for s in stocks]
    confidences = [s["confidence_score"] for s in stocks]
    
    fig = go.Figure(data=[go.Scatter(
        x=list(range(len(tickers))),
        y=confidences,
        mode='lines+markers+text',
        text=tickers,
        textposition='top center',
        line=dict(color='steelblue'),
        marker=dict(size=10)
    )])
    fig.update_layout(
        title='Earnings Impact Timeline',
        xaxis_title='Stock Index',
        yaxis_title='Confidence Score',
        height=400
    )
    
    return jsonify(json.loads(fig.to_json()))


def main():
    """Start the dashboard server."""
    port = 8080
    
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║         SPY OPTIONS TRADING DASHBOARD SERVER                   ║
    ║                                                                ║
    ║  🚀 Starting server...                                         ║
    ║  📊 Open your browser to: http://localhost:8080               ║
    ║                                                                ║
    ║  Features:                                                     ║
    ║  • Live dashboard with all analysis                           ║
    ║  • 🔄 Update Analysis button to rerun analysis                ║
    ║  • Real-time data from yfinance & Finnhub                     ║
    ║                                                                ║
    ║  Press CTRL+C to stop the server                              ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    
    try:
        app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False)
    except KeyboardInterrupt:
        print("\n\n✋ Server stopped by user")
        sys.exit(0)


if __name__ == '__main__':
    main()
