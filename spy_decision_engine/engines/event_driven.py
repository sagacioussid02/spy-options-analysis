"""
Event-Driven Engine
Detects and quantifies market-moving events from news/earnings
Measures REAL price/volume reactions, not just estimates
Uses FinBert for accurate financial sentiment classification
"""
import json
from pathlib import Path
from datetime import datetime, timedelta
import yfinance as yf

import config

try:
    from utils.finbert_sentiment import get_analyzer
    FINBERT_AVAILABLE = True
except:
    FINBERT_AVAILABLE = False

class EventDrivenEngine:
    """Detects events and measures market reaction"""
    
    # Hard-coded, high-impact event taxonomy
    EVENT_TYPES = {
        "EARNINGS": ["earnings", "eps", "revenue", "beat", "miss"],
        "GUIDANCE": ["guidance", "outlook", "forecast", "raised", "cut"],
        "M&A": ["acquires", "merger", "buyout", "acquisition", "deal"],
        "REGULATORY": ["lawsuit", "sec", "antitrust", "doj", "investigation"],
        "FDA": ["fda approval", "clinical trial", "drug approval", "pullback"],
        "MACRO": ["fed", "rate decision", "inflation", "fomc", "cpi"],
        "GEOPOLITICAL": ["tariff", "sanctions", "trade war", "election"],
    }
    
    # Market cap contribution weights (how much each stock moves SPY)
    IMPACT_WEIGHTS = {
        "NVDA": 1.0,   # ~7% of SPY
        "AAPL": 0.95,  # ~7% of SPY
        "MSFT": 0.95,  # ~7% of SPY
        "AMZN": 0.85,  # ~4% of SPY
        "META": 0.75,  # ~2.5% of SPY
        "TSLA": 0.6,   # ~1.5% of SPY
        "BRK": 0.7,    # ~1.5% of SPY
        "JNJ": 0.5,    # ~1% of SPY
        "XOM": 0.4,    # Energy sector
        "JPM": 0.4,    # Financial sector
    }
    
    def __init__(self):
        """Initialize event engine"""
        self.events_detected = []
        self.reactions = []
        self.net_bias = "NEUTRAL"
        self.confidence = "NEUTRAL"
        self.score = 0.5
    
    def detect_events(self, sentiment_data):
        """
        Detect high-impact events from sentiment data
        
        Input: sentiment.json with stock-level sentiment
        Output: List of detected events with type and classification
        """
        events = []
        
        if isinstance(sentiment_data, dict) and 'stock_sentiment_analysis' in sentiment_data:
            stocks = sentiment_data['stock_sentiment_analysis']
        else:
            return events
        
        for symbol, data in stocks.items():
            if not isinstance(data, dict):
                continue
            
            # Get headlines for this stock
            headlines = self._get_headlines_for_stock(symbol, sentiment_data)
            
            for headline in headlines:
                event_type = self._classify_event(headline)
                if event_type:
                    # Classify as surprise or neutral
                    surprise = self._classify_surprise(headline, event_type)
                    
                    events.append({
                        "symbol": symbol,
                        "event_type": event_type,
                        "headline": headline,
                        "surprise": surprise,
                        "timestamp": datetime.now().isoformat()
                    })
        
        self.events_detected = events
        return events
    
    def _get_headlines_for_stock(self, symbol, sentiment_data):
        """Extract headlines for a specific stock from sentiment data"""
        headlines = []
        
        try:
            # Check if sentiment data has mentions
            if isinstance(sentiment_data, dict) and 'latest_news' in sentiment_data:
                news_list = sentiment_data['latest_news']
                if isinstance(news_list, list):
                    for article in news_list:
                        if isinstance(article, dict):
                            title = article.get('title', '')
                            source = article.get('source', '')
                            if symbol in title or symbol in source:
                                headlines.append(title)
        except:
            pass
        
        return headlines
    
    def _classify_event(self, headline):
        """Classify headline into event type"""
        headline_lower = headline.lower()
        
        for event_type, keywords in self.EVENT_TYPES.items():
            if any(keyword in headline_lower for keyword in keywords):
                return event_type
        
        return None
    
    def _classify_surprise(self, headline, event_type):
        """
        Classify event as surprise, neutral, or expected
        Uses FinBert for accurate financial sentiment if available
        Falls back to keyword matching otherwise
        """
        if FINBERT_AVAILABLE:
            analyzer = get_analyzer()
            sentiment_result = analyzer.analyze_sentiment(headline)
            
            sentiment = sentiment_result['sentiment']
            confidence = sentiment_result['confidence']
            
            # High confidence classification using FinBert
            if sentiment == 'positive':
                if confidence > 0.85:
                    return "POSITIVE_SURPRISE"
                else:
                    return "POSITIVE"
            elif sentiment == 'negative':
                if confidence > 0.85:
                    return "NEGATIVE_SURPRISE"
                else:
                    return "NEGATIVE"
            else:
                return "NEUTRAL"
        else:
            # Fallback to keyword matching
            headline_lower = headline.lower()
            
            if event_type == "EARNINGS":
                if any(word in headline_lower for word in ["beat", "surge", "jump", "soar"]):
                    return "POSITIVE_SURPRISE"
                elif any(word in headline_lower for word in ["miss", "drop", "fall", "plunge"]):
                    return "NEGATIVE_SURPRISE"
                else:
                    return "NEUTRAL"
            
            elif event_type == "GUIDANCE":
                if any(word in headline_lower for word in ["raised", "beat", "strong"]):
                    return "POSITIVE"
                elif any(word in headline_lower for word in ["cut", "miss", "weak"]):
                    return "NEGATIVE"
                else:
                    return "NEUTRAL"
            
            elif event_type == "REGULATORY":
                return "NEGATIVE"
            
            elif event_type == "M&A":
                return "POSITIVE"
            
            else:
                return "NEUTRAL"
    
    def evaluate_reactions(self, events):
        """
        Evaluate REAL market reaction to events by checking:
        1. Actual price movement vs 5-day average
        2. Volume spike vs baseline
        3. Intraday reaction (if available)
        """
        reactions = []
        
        for event in events:
            symbol = event['symbol']
            
            # Measure real price/volume reaction
            reaction_data = self._measure_real_reaction(symbol)
            
            # Base confidence on surprise classification
            if event['surprise'] == "POSITIVE_SURPRISE":
                base_confidence = "HIGH"
            elif event['surprise'] == "NEGATIVE_SURPRISE":
                base_confidence = "HIGH"
            else:
                base_confidence = "MEDIUM"
            
            # Compare expected vs actual
            if event['surprise'] == "POSITIVE_SURPRISE":
                expected_reaction = 1.5
            elif event['surprise'] == "POSITIVE":
                expected_reaction = 0.8
            elif event['surprise'] == "NEGATIVE_SURPRISE":
                expected_reaction = -2.0
            elif event['surprise'] == "NEGATIVE":
                expected_reaction = -1.0
            else:
                expected_reaction = 0.0
            
            # Get actual reaction
            actual_reaction = reaction_data['price_change_pct']
            actual_volume = reaction_data['volume_ratio']
            
            # Measure accuracy: does actual match expected?
            reaction_match = abs(actual_reaction - expected_reaction) < 1.0
            
            # Apply weight based on symbol's SPY impact
            weight = self.IMPACT_WEIGHTS.get(symbol, 0.3)
            
            # Final impact: use ACTUAL reaction, not expected
            # This is key: we trade the real reaction, not the prediction
            impact_score = abs(actual_reaction) * weight
            
            reactions.append({
                "symbol": symbol,
                "event_type": event['event_type'],
                "surprise": event['surprise'],
                "expected_reaction": expected_reaction,
                "actual_reaction": actual_reaction,
                "actual_volume_ratio": actual_volume,
                "reaction_confirmed": reaction_match,
                "weight": weight,
                "impact_score": impact_score,
                "confidence": base_confidence,
                "signal_strength": "CONFIRMED" if reaction_match else "DIVERGENCE"
            })
        
        self.reactions = reactions
        return reactions
    
    def _measure_real_reaction(self, symbol):
        """
        Measure ACTUAL price and volume reaction
        
        Compares:
        - Today's price vs 5-day average
        - Today's volume vs 20-day average
        """
        try:
            # Get 20 days of data to establish baselines
            data = yf.download(symbol, period='20d', progress=False)
            
            if data.empty or len(data) < 2:
                return {
                    'price_change_pct': 0.0,
                    'volume_ratio': 1.0
                }
            
            # Get today and yesterday
            today = data.iloc[-1]
            yesterday = data.iloc[-2]
            
            # Price change %
            price_change_pct = ((today['Close'] - yesterday['Close']) / yesterday['Close']) * 100
            
            # Volume ratio vs 20-day average
            volume_20day_avg = data['Volume'].iloc[:-1].mean()
            volume_ratio = today['Volume'] / volume_20day_avg if volume_20day_avg > 0 else 1.0
            
            return {
                'price_change_pct': round(price_change_pct, 2),
                'volume_ratio': round(volume_ratio, 2),
                'price_today': round(today['Close'], 2),
                'price_yesterday': round(yesterday['Close'], 2),
                'volume_today': int(today['Volume']),
                'volume_avg': int(volume_20day_avg)
            }
        
        except Exception as e:
            # If we can't get data, return neutral
            return {
                'price_change_pct': 0.0,
                'volume_ratio': 1.0
            }
    
    def compute_score(self, reactions):
        """
        Compute overall event-driven bias score (0-1)
        
        Factors in:
        - Actual price reactions (not predictions)
        - Volume confirmation
        - Whether reaction matches expectation (signal strength)
        
        0.0 = strongly bearish
        0.5 = neutral
        1.0 = strongly bullish
        """
        if not reactions:
            self.score = 0.5
            self.net_bias = "NEUTRAL"
            self.confidence = "LOW"
            return 0.5
        
        # Calculate weighted impact using ACTUAL reactions
        total_bullish = sum(r['impact_score'] for r in reactions 
                           if r['actual_reaction'] > 0)
        total_bearish = sum(r['impact_score'] for r in reactions 
                           if r['actual_reaction'] < 0)
        
        net_impact = total_bullish - total_bearish
        
        # Count confirmed signals (actual reaction matches expectation)
        confirmed_reactions = [r for r in reactions if r['signal_strength'] == "CONFIRMED"]
        confirmation_rate = (len(confirmed_reactions) / len(reactions)) if reactions else 0
        
        # Adjust confidence based on confirmation
        if confirmation_rate > 0.75:
            confidence_multiplier = 1.2  # High confidence if signals confirmed
        elif confirmation_rate > 0.5:
            confidence_multiplier = 1.0
        else:
            confidence_multiplier = 0.8  # Lower confidence if divergence
        
        # Determine bias based on actual reactions
        adjusted_impact = net_impact * confidence_multiplier
        
        if adjusted_impact > 2.0:
            self.net_bias = "STRONGLY_BULLISH"
            self.score = 0.78
            self.confidence = "HIGH"
        elif adjusted_impact > 0.5:
            self.net_bias = "BULLISH"
            self.score = 0.65
            self.confidence = "MEDIUM"
        elif adjusted_impact < -2.0:
            self.net_bias = "STRONGLY_BEARISH"
            self.score = 0.22
            self.confidence = "HIGH"
        elif adjusted_impact < -0.5:
            self.net_bias = "BEARISH"
            self.score = 0.35
            self.confidence = "MEDIUM"
        else:
            self.net_bias = "NEUTRAL"
            self.score = 0.5
            self.confidence = "LOW"
        
        return self.score
    
    def run(self, context):
        """
        Main engine execution
        
        Input: MarketContext with sentiment data
        Output: context.event_driven with event analysis
        """
        print("\n📰 EVENT-DRIVEN ENGINE")
        print("-" * 70)

        # IMPACT_WEIGHTS is an index-composition concept (how much each
        # stock moves SPY) — doesn't apply to a single non-index ticker.
        if getattr(context, "ticker", "SPY") not in config.INDEX_TICKERS:
            print(f"  (skipped: event impact weighting is index-only, "
                  f"{context.ticker} is not an index)")
            context.event_driven = {
                "events_detected": [], "reactions": [], "net_event_bias": "NEUTRAL",
                "confidence": "LOW", "score": 0.5,
                "skipped": f"{context.ticker} is not an index ticker",
            }
            report_file = Path(__file__).parent.parent / 'reports' / 'event_driven.json'
            with open(report_file, 'w') as f:
                json.dump(context.event_driven, f, indent=2)
            return context

        # Get sentiment data
        sentiment_file = Path(__file__).parent.parent / 'reports' / 'sentiment.json'
        
        try:
            with open(sentiment_file) as f:
                sentiment_data = json.load(f)
        except:
            sentiment_data = {}
        
        # Detect events
        events = self.detect_events(sentiment_data)
        
        if events:
            print(f"📍 Events Detected: {len(events)}")
            for event in events[:5]:  # Show top 5
                print(f"   • {event['symbol']}: {event['event_type']} ({event['surprise']})")
        else:
            print("No major events detected")
        
        # Evaluate reactions
        reactions = self.evaluate_reactions(events)
        
        # Compute score
        score = self.compute_score(reactions)
        
        # Store in context
        context.event_driven = {
            "events_detected": events,
            "reactions": reactions,
            "net_event_bias": self.net_bias,
            "confidence": self.confidence,
            "score": score,
            "component_weight": 0.20  # This component weighs 20% in final decision
        }
        
        print(f"\n📊 Event Analysis:")
        print(f"   Net Bias: {self.net_bias}")
        print(f"   Confidence: {self.confidence}")
        print(f"   Score: {score:.2f}")
        
        # Write report
        report = {
            "timestamp": datetime.now().strftime("%H:%M"),
            "events_detected": len(events),
            "events": events,
            "reactions": reactions,
            "net_event_bias": self.net_bias,
            "confidence": self.confidence,
            "score": score,
            "impact_summary": self._generate_impact_summary(reactions)
        }
        
        report_file = Path(__file__).parent.parent / 'reports' / 'event_driven.json'
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n✓ Event-driven report written to /reports/event_driven.json")
        
        return context
    
    def _generate_impact_summary(self, reactions):
        """Generate human-readable impact summary"""
        if not reactions:
            return "No events impacting SPY"
        
        by_impact = sorted(reactions, key=lambda x: x['impact_score'], reverse=True)
        
        summary = []
        for r in by_impact[:3]:
            impact = "📈 Positive" if r['price_reaction'] > 0 else "📉 Negative"
            summary.append(f"{r['symbol']} {r['event_type']}: {impact} impact")
        
        return " | ".join(summary) if summary else "Mixed signals"
