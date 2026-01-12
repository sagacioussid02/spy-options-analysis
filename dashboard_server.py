#!/usr/bin/env python3
"""
Dashboard Web Server - Serves the SPY trading dashboard with live analysis updates
Allows running analysis and updating dashboard in real-time
"""

import json
import subprocess
import sys
from pathlib import Path
from flask import Flask, render_template_string, jsonify
from datetime import datetime

app = Flask(__name__)

# Get reports directory
REPORTS_DIR = Path(__file__).parent / "spy_decision_engine" / "reports"
DASHBOARD_HTML = REPORTS_DIR / "dashboard.html"
MAIN_SCRIPT = Path(__file__).parent / "spy_decision_engine" / "main.py"


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
