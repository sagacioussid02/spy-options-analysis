"""
Shared context object for all engines to communicate.
All engines read from and write to this context.
"""


class MarketContext:
    """Central context object holding all engine outputs."""
    
    def __init__(self, ticker: str = "SPY"):
        """
        Initialize context.
        
        Args:
            ticker: Stock ticker symbol (default: SPY for market-wide analysis)
        """
        self.ticker = ticker
        self.market_snapshot = None
        self.news_sentiment = None
        self.spy_momentum = None
        self.volatility = None
        self.options_analysis = None
        self.final_decision = None
