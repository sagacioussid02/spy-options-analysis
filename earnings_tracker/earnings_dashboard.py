#!/usr/bin/env python3
"""
Earnings Tracker 3D Visualization Dashboard
Interactive charts for earnings confidence analysis using Plotly
"""

from flask import Flask, render_template, jsonify
from pathlib import Path
import json
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px
from earnings_analyzer import EarningsAnalyzer

app = Flask(__name__)
analyzer = EarningsAnalyzer()

# Ensure templates directory exists
template_dir = Path(__file__).parent / "templates"
template_dir.mkdir(exist_ok=True)

@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('earnings_dashboard.html')

@app.route('/api/earnings-data')
def get_earnings_data():
    """Get earnings analysis data."""
    analysis = analyzer.analyze_all_stocks()
    return jsonify(analysis)

@app.route('/api/3d-confidence-chart')
def get_3d_confidence_chart():
    """Generate 3D scatter chart: Ticker vs Confidence vs Sentiment."""
    analysis = analyzer.analyze_all_stocks()
    stocks = analysis.get("stocks", [])
    
    tickers = [s["ticker"] for s in stocks]
    confidences = [s["confidence_score"] for s in stocks]
    sentiments = [s["sentiment_analysis"].get("score", 0) for s in stocks]
    colors = [s["sentiment_analysis"].get("score", 0) for s in stocks]
    
    fig = go.Figure(data=[go.Scatter3d(
        x=tickers,
        y=confidences,
        z=sentiments,
        mode='markers+text',
        text=tickers,
        textposition='top center',
        marker=dict(
            size=12,
            color=colors,
            colorscale='RdYlGn',
            showscale=True,
            colorbar=dict(title="Sentiment<br>Score"),
            line=dict(color='darkblue', width=2)
        ),
        textfont=dict(size=10, color='darkblue')
    )])
    
    fig.update_layout(
        title="3D Earnings Confidence Analysis<br><sub>Ticker vs Confidence Score vs Sentiment</sub>",
        scene=dict(
            xaxis=dict(title="Ticker", showgrid=True),
            yaxis=dict(title="Confidence Score (0-100)", showgrid=True),
            zaxis=dict(title="Sentiment Score (-1 to 1)", showgrid=True),
            bgcolor="rgba(240, 240, 240, 0.9)"
        ),
        width=1000,
        height=700,
        hovermode='closest',
        font=dict(size=11)
    )
    
    return json.loads(fig.to_json())

@app.route('/api/component-scores-3d')
def get_component_scores_3d():
    """Generate 3D bar chart of component scores breakdown."""
    analysis = analyzer.analyze_all_stocks()
    stocks = analysis.get("stocks", [])
    
    # Get first 5 stocks for cleaner visualization
    top_stocks = stocks[:5]
    
    tickers = [s["ticker"] for s in top_stocks]
    valuation = [s["component_scores"].get("valuation", 0) for s in top_stocks]
    beat_consistency = [s["component_scores"].get("beat_consistency", 0) for s in top_stocks]
    volatility_risk = [s["component_scores"].get("volatility_risk", 0) for s in top_stocks]
    move_predictability = [s["component_scores"].get("move_predictability", 0) for s in top_stocks]
    growth = [s["component_scores"].get("growth", 0) for s in top_stocks]
    time_decay = [s["component_scores"].get("time_decay", 0) for s in top_stocks]
    news_sentiment = [s["component_scores"].get("news_sentiment", 50) for s in top_stocks]
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(x=tickers, y=valuation, name='Valuation', marker_color='#1f77b4'))
    fig.add_trace(go.Bar(x=tickers, y=beat_consistency, name='Beat Consistency', marker_color='#ff7f0e'))
    fig.add_trace(go.Bar(x=tickers, y=volatility_risk, name='Volatility Risk', marker_color='#2ca02c'))
    fig.add_trace(go.Bar(x=tickers, y=move_predictability, name='Move Predictability', marker_color='#d62728'))
    fig.add_trace(go.Bar(x=tickers, y=growth, name='Growth Score', marker_color='#9467bd'))
    fig.add_trace(go.Bar(x=tickers, y=time_decay, name='Time Decay', marker_color='#8c564b'))
    fig.add_trace(go.Bar(x=tickers, y=news_sentiment, name='News Sentiment', marker_color='#e377c2'))
    
    fig.update_layout(
        title="Component Scores Breakdown (Top 5 Stocks)<br><sub>FinBERT Sentiment included</sub>",
        barmode='group',
        xaxis_title="Ticker",
        yaxis_title="Score (0-100)",
        height=600,
        width=1000,
        hovermode='x',
        plot_bgcolor="rgba(240, 240, 240, 0.5)",
        font=dict(size=11)
    )
    
    return json.loads(fig.to_json())

@app.route('/api/confidence-vs-sentiment')
def get_confidence_vs_sentiment():
    """Generate 2D scatter: Confidence vs Sentiment with size = IV Rank."""
    analysis = analyzer.analyze_all_stocks()
    stocks = analysis.get("stocks", [])
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=[s["sentiment_analysis"].get("score", 0) for s in stocks],
        y=[s["confidence_score"] for s in stocks],
        mode='markers+text',
        text=[s["ticker"] for s in stocks],
        textposition='top center',
        marker=dict(
            size=[s["component_scores"].get("volatility_risk", 50) / 5 for s in stocks],
            color=[s["sentiment_analysis"].get("confidence", 0.5) for s in stocks],
            colorscale='Viridis',
            showscale=True,
            colorbar=dict(title="Sentiment<br>Confidence"),
            line=dict(color='darkblue', width=2),
            opacity=0.7
        ),
        hovertemplate='<b>%{text}</b><br>Sentiment: %{x:.3f}<br>Confidence: %{y:.1f}%<extra></extra>'
    ))
    
    fig.update_layout(
        title="Confidence vs Sentiment Score<br><sub>Bubble size = Volatility Risk</sub>",
        xaxis_title="Sentiment Score (-1 to 1)",
        yaxis_title="Confidence Score (0-100)",
        height=600,
        width=1000,
        hovermode='closest',
        plot_bgcolor="rgba(240, 240, 240, 0.5)",
        font=dict(size=11)
    )
    
    return json.loads(fig.to_json())

@app.route('/api/earnings-calendar')
def get_earnings_calendar():
    """Generate earnings calendar timeline."""
    analysis = analyzer.analyze_all_stocks()
    stocks = analysis.get("stocks", [])
    
    fig = go.Figure()
    
    for stock in stocks:
        fig.add_trace(go.Scatter(
            x=[stock["earnings_date"]],
            y=[stock["confidence_score"]],
            mode='markers+text',
            text=[stock["ticker"]],
            textposition='top center',
            marker=dict(
                size=15,
                color=stock["confidence_score"],
                colorscale='RdYlGn',
                showscale=False,
                line=dict(color='darkblue', width=2)
            ),
            name=stock["ticker"],
            hovertemplate=f"<b>{stock['ticker']}</b><br>Date: {stock['earnings_date']}<br>Confidence: {stock['confidence_score']}%<br>Sentiment: {stock['sentiment_analysis'].get('sentiment', 'neutral')}<extra></extra>"
        ))
    
    fig.update_layout(
        title="Earnings Calendar - Confidence by Date<br><sub>Sorted by upcoming earnings dates</sub>",
        xaxis_title="Earnings Date",
        yaxis_title="Confidence Score (0-100)",
        height=500,
        width=1000,
        hovermode='closest',
        plot_bgcolor="rgba(240, 240, 240, 0.5)",
        font=dict(size=11),
        showlegend=False
    )
    
    return json.loads(fig.to_json())

@app.route('/api/sentiment-distribution')
def get_sentiment_distribution():
    """Generate pie/gauge charts for sentiment distribution."""
    analysis = analyzer.analyze_all_stocks()
    stocks = analysis.get("stocks", [])
    
    positive = len([s for s in stocks if s["sentiment_analysis"].get("sentiment") == "positive"])
    negative = len([s for s in stocks if s["sentiment_analysis"].get("sentiment") == "negative"])
    neutral = len([s for s in stocks if s["sentiment_analysis"].get("sentiment") == "neutral"])
    
    fig = go.Figure(data=[go.Pie(
        labels=['Positive', 'Negative', 'Neutral'],
        values=[positive, negative, neutral],
        marker=dict(colors=['#2ca02c', '#d62728', '#ff7f0e']),
        hole=.3
    )])
    
    fig.update_layout(
        title="Sentiment Distribution Across Watchlist<br><sub>FinBERT Analysis</sub>",
        height=500,
        width=500,
        font=dict(size=11)
    )
    
    return json.loads(fig.to_json())

@app.route('/api/summary-metrics')
def get_summary_metrics():
    """Get summary metrics for the dashboard."""
    analysis = analyzer.analyze_all_stocks()
    summary = analysis.get("summary", {})
    
    return jsonify({
        "total_stocks": analysis.get("total_stocks", 0),
        "avg_confidence": summary.get("avg_confidence", 0),
        "highest_confidence": summary.get("highest_confidence", 0),
        "lowest_confidence": summary.get("lowest_confidence", 0),
        "very_high_count": summary.get("very_high_count", 0),
        "high_count": summary.get("high_count", 0),
        "moderate_count": summary.get("moderate_count", 0),
        "low_count": summary.get("low_count", 0),
        "finbert_available": analysis.get("finbert_available", False),
        "timestamp": analysis.get("timestamp", "")
    })

if __name__ == '__main__':
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║      EARNINGS TRACKER 3D VISUALIZATION DASHBOARD              ║
    ║                                                                ║
    ║  🚀 Starting server...                                         ║
    ║  📊 Open your browser to: http://localhost:8081               ║
    ║                                                                ║
    ║  Features:                                                     ║
    ║  • 3D Confidence Analysis (Ticker vs Confidence vs Sentiment) ║
    ║  • Component Scores Breakdown                                 ║
    ║  • Confidence vs Sentiment Scatter                            ║
    ║  • Earnings Calendar Timeline                                 ║
    ║  • Sentiment Distribution (FinBERT)                           ║
    ║  • Real-time Summary Metrics                                  ║
    ║                                                                ║
    ║  Press CTRL+C to stop the server                              ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    app.run(debug=False, port=8081, host='0.0.0.0')
