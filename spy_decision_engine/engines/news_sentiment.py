"""
News Sentiment Engine

Pulls recent headlines and analyzes sentiment using FinBert AI model.
Falls back to keyword matching if FinBert unavailable.
Calculates sentiment scores for each individual stock in top 10 SPY holdings.
"""
import json
import os
from typing import Dict, List

from context.market_context import MarketContext
from utils.data_fetcher import get_news_headlines
from utils.scoring import calculate_sentiment_score
import config

try:
    from utils.finbert_sentiment import get_analyzer, analyze_stock_sentiment
    FINBERT_AVAILABLE = True
except:
    FINBERT_AVAILABLE = False
    analyze_stock_sentiment = None


class NewsSentimentEngine:
    """Analyzes news sentiment for market and individual stocks."""
    
    def __init__(self):
        self.positive_keywords = config.POSITIVE_KEYWORDS
        self.negative_keywords = config.NEGATIVE_KEYWORDS
        # Top 10 SPY holdings + SPY itself for tracking
        self.stocks_to_track = {
            "NVIDIA": ["nvidia", "nvda"],
            "Apple": ["apple", "aapl"],
            "Microsoft": ["microsoft", "msft"],
            "Amazon": ["amazon", "amzn"],
            "Meta": ["meta", "facebook", "fb"],
            "Google": ["google", "alphabet", "googl"],
            "Tesla": ["tesla", "tsla"],
            "Berkshire": ["berkshire", "brk"],
            "JPMorgan": ["jpmorgan", "jpm"],
            "SPY": ["spy", "s&p 500"]
        }
        # Ticker to company name mapping
        self.ticker_to_company = {
            "NVDA": "NVIDIA",
            "AAPL": "Apple",
            "MSFT": "Microsoft",
            "AMZN": "Amazon",
            "META": "Meta",
            "GOOGL": "Google",
            "TSLA": "Tesla",
            "BRK": "Berkshire",
            "JPM": "JPMorgan",
            "SPY": "SPY"
        }
    
    def run(self, context: MarketContext) -> None:
        """
        Execute news sentiment analysis.
        
        Args:
            context: Shared market context to write results to
        """
        # Fetch headlines - for specific ticker or all for SPY
        headlines = get_news_headlines(ticker=context.ticker)
        
        # If analyzing specific ticker, only track that ticker
        if context.ticker != "SPY":
            # Map ticker to company name
            company_name = self.ticker_to_company.get(context.ticker, context.ticker)
            stocks_to_analyze = {company_name: self.stocks_to_track.get(company_name, [context.ticker.lower()])}
        else:
            stocks_to_analyze = self.stocks_to_track
        
        # Initialize sentiment tracking for each stock
        stock_sentiment = {stock: {
            "positive": 0, 
            "negative": 0, 
            "count": 0,
            "score": 0.5,  # Default neutral
            "headlines": []
        } for stock in stocks_to_analyze.keys()}
        
        # Overall sentiment counters
        total_positive = 0
        total_negative = 0
        
        # Analyze each headline
        for headline in headlines:
            headline_lower = headline.lower()
            
            # Find which stocks are mentioned in this headline
            mentioned_stocks = set()
            for stock_name, keywords in stocks_to_analyze.items():
                for keyword in keywords:
                    if keyword in headline_lower:
                        mentioned_stocks.add(stock_name)
                        stock_sentiment[stock_name]["count"] += 1
                        stock_sentiment[stock_name]["headlines"].append(headline)
                        break
            
            # Analyze sentiment - use FinBert if available, else keyword matching
            if FINBERT_AVAILABLE:
                analyzer = get_analyzer()
                sentiment_result = analyzer.analyze_sentiment(headline)
                sentiment = sentiment_result['sentiment']
                
                if sentiment == 'positive':
                    positive_matches = 1
                    negative_matches = 0
                elif sentiment == 'negative':
                    positive_matches = 0
                    negative_matches = 1
                else:
                    positive_matches = 0
                    negative_matches = 0
            else:
                # Fallback to keyword matching
                positive_matches = sum(1 for word in self.positive_keywords if word in headline_lower)
                negative_matches = sum(1 for word in self.negative_keywords if word in headline_lower)
            
            total_positive += positive_matches
            total_negative += negative_matches
            
            # Attribute sentiment to mentioned stocks
            for stock in mentioned_stocks:
                stock_sentiment[stock]["positive"] += positive_matches
                stock_sentiment[stock]["negative"] += negative_matches
        
        # Calculate individual stock sentiment scores
        for stock, data in stock_sentiment.items():
            if data["count"] > 0:
                data["score"] = calculate_sentiment_score(data["positive"], data["negative"])
                # Keep only most recent 3 headlines per stock
                data["headlines"] = data["headlines"][-3:]
            else:
                data["score"] = 0.5  # Neutral if no mentions
        
        # Calculate overall market sentiment score
        overall_sentiment_score = calculate_sentiment_score(total_positive, total_negative)
        
        # Get direct FinBert sentiment for stocks mentioned in headlines (faster)
        direct_stock_sentiment = {}
        if FINBERT_AVAILABLE:
            print("  Analyzing direct FinBert sentiment for mentioned stocks...")
            stock_mapping = {
                "NVIDIA": "NVDA",
                "Apple": "AAPL",
                "Microsoft": "MSFT",
                "Amazon": "AMZN",
                "Meta": "META",
                "Google": "GOOGL",
                "Tesla": "TSLA",
                "Berkshire": "BRK",
                "JPMorgan": "JPM",
                "SPY": "SPY"
            }
            
            try:
                # Only analyze top 5 mentioned stocks for speed
                top_stocks = sorted(
                    [(s, d["count"]) for s, d in stock_sentiment.items() if d["count"] > 0],
                    key=lambda x: x[1],
                    reverse=True
                )[:5]
                
                for stock_name, _ in top_stocks:
                    stock_symbol = stock_mapping.get(stock_name, stock_name)
                    print(f"    Querying {stock_symbol}...", end=" ", flush=True)
                    direct_result = analyze_stock_sentiment(stock_symbol, stock_name)
                    direct_stock_sentiment[stock_symbol] = direct_result
                    print("✓")
            except Exception as e:
                print(f"    Warning: Direct FinBert analysis skipped: {e}")
        
        # Helper to get direct sentiment for a stock
        def get_direct_finbert_result(stock_name: str) -> Dict:
            stock_mapping = {
                "NVIDIA": "NVDA",
                "Apple": "AAPL",
                "Microsoft": "MSFT",
                "Amazon": "AMZN",
                "Meta": "META",
                "Google": "GOOGL",
                "Tesla": "TSLA",
                "Berkshire": "BRK",
                "JPMorgan": "JPM",
                "SPY": "SPY"
            }
            symbol = stock_mapping.get(stock_name, stock_name)
            return direct_stock_sentiment.get(symbol, None)
        
        # Blend headline sentiment with direct FinBert sentiment
        def blend_sentiment(headline_score: float, mentions: int, direct_result: Dict) -> Dict:
            """
            Combine headline sentiment with direct FinBert sentiment.
            
            Weighting:
            - Headline sentiment: weighted by mention count (more mentions = more evidence)
            - Direct FinBert: weighted by its confidence score
            
            Returns blended score and confidence
            """
            if direct_result is None:
                # No direct query, just use headline sentiment
                return {
                    "blended_score": headline_score,
                    "blended_sentiment": "positive" if headline_score > 0.6 else ("negative" if headline_score < 0.4 else "neutral"),
                    "sources": ["headlines_only"]
                }
            
            # Both sources available - blend them
            # Weight by mention count (max weight 1.0 for 5+ mentions) and confidence
            mention_weight = min(mentions / 5.0, 1.0)  # 0-1 scale
            direct_weight = direct_result['confidence']  # 0-1 scale (confidence)
            
            # Normalize weights
            total_weight = mention_weight + direct_weight
            if total_weight == 0:
                return {
                    "blended_score": headline_score,
                    "blended_sentiment": "positive" if headline_score > 0.6 else ("negative" if headline_score < 0.4 else "neutral"),
                    "sources": ["headlines_only"]
                }
            
            headline_weight = mention_weight / total_weight
            direct_weight = direct_weight / total_weight
            
            # Blend the scores
            blended_score = (headline_score * headline_weight) + (direct_result['score'] * direct_weight)
            
            # Determine blended sentiment
            if blended_score > 0.3:
                blended_sentiment = "positive"
            elif blended_score < -0.3:
                blended_sentiment = "negative"
            else:
                blended_sentiment = "neutral"
            
            return {
                "blended_score": round(blended_score, 3),
                "blended_sentiment": blended_sentiment,
                "sources": ["headlines", "direct_finbert"],
                "weights": {
                    "headlines": round(headline_weight, 2),
                    "direct_finbert": round(direct_weight, 2)
                },
                "headline_contribution": round(headline_score * headline_weight, 3),
                "finbert_contribution": round(direct_result['score'] * direct_weight, 3)
            }
        
        # Build output with blended sentiment
        by_stock_dict = {}
        total_blended_positive = 0
        total_blended_negative = 0
        
        for stock, data in stock_sentiment.items():
            if data["count"] > 0:  # Only include stocks that were mentioned
                direct_result = get_direct_finbert_result(stock)
                blended = blend_sentiment(data["score"], data["count"], direct_result)
                
                # Track blended sentiment for overall calculation
                if blended["blended_sentiment"] == "positive":
                    total_blended_positive += 1
                elif blended["blended_sentiment"] == "negative":
                    total_blended_negative += 1
                
                by_stock_dict[stock] = {
                    "headline_score": round(data["score"], 2),
                    "headline_sentiment": "positive" if data["score"] > 0.6 else ("negative" if data["score"] < 0.4 else "neutral"),
                    "mentions": data["count"],
                    "recent_headlines": data["headlines"],
                    "direct_finbert": direct_result,
                    "blended": blended
                }
        
        # Calculate overall blended sentiment
        overall_blended_score = (total_blended_positive - total_blended_negative) / max(len(by_stock_dict), 1) if by_stock_dict else 0.0
        
        # Build output with both headline-based and direct sentiment
        output = {
            "overall": {
                "positive_count": total_positive,
                "negative_count": total_negative,
                "headline_score": round(overall_sentiment_score, 2),
                "blended_positive": total_blended_positive,
                "blended_negative": total_blended_negative,
                "blended_score": round(overall_blended_score, 2),
            },
            "top_headlines": headlines[:15],  # Top 15 headlines from all sources
            "by_stock": by_stock_dict,
            "direct_finbert_all_stocks": direct_stock_sentiment,
            "analysis_method": "FinBert AI (Headlines + Direct Query + Blended)" if FINBERT_AVAILABLE else "Keyword Matching"
        }
        
        # Write to context
        context.news_sentiment = output
        
        # Write to JSON file
        self._write_report(output)
    
    def _write_report(self, output: Dict) -> None:
        """Write sentiment report to JSON file."""
        report_path = os.path.join(config.REPORTS_DIR, "sentiment.json")
        with open(report_path, "w") as f:
            json.dump(output, f, indent=2)
        print(f"✓ News Sentiment report written to {report_path}")
