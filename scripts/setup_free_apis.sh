#!/bin/bash
# Setup script for installing free API dependencies

echo "=========================================="
echo "SPY Decision Engine - API Setup"
echo "=========================================="
echo ""

# Install required Python packages
echo "📦 Installing required Python packages..."
pip install yfinance requests -q

if [ $? -eq 0 ]; then
    echo "✓ yfinance and requests installed"
else
    echo "❌ Error installing packages"
    exit 1
fi

echo ""
echo "=========================================="
echo "FREE API SETUP COMPLETE"
echo "=========================================="
echo ""
echo "You now have:"
echo "✓ yfinance - Free stock data (no API key needed)"
echo "✓ requests - For HTTP requests to NewsAPI"
echo ""
echo "OPTIONAL: News API Setup"
echo "----------------------------------------"
echo "To get real news headlines, set up NewsAPI:"
echo ""
echo "1. Go to: https://newsapi.org"
echo "2. Sign up for free account (no credit card needed)"
echo "3. Copy your API key"
echo "4. Set environment variable:"
echo ""
echo "   export NEWS_API_KEY=\"your_api_key_here\""
echo ""
echo "Or add to your shell config (~/.bashrc, ~/.zshrc):"
echo '   echo "export NEWS_API_KEY=\"your_api_key_here\"" >> ~/.bashrc'
echo ""
echo "Then run the engine:"
echo "   cd spy_decision_engine"
echo "   python3 main.py"
echo ""
echo "Without NEWS_API_KEY, the engine will use mock headlines."
echo ""
