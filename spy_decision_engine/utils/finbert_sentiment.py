"""
FinBert Sentiment Analysis
Uses pre-trained FinBert model for financial sentiment classification
Much more accurate than keyword matching for financial news
"""
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from typing import Dict, List, Tuple

class FinBertSentimentAnalyzer:
    """
    Financial sentiment analyzer using FinBert
    
    FinBert is pre-trained on financial news and SEC filings
    Returns: sentiment score (-1 to 1) and confidence
    """
    
    def __init__(self):
        """Initialize FinBert model"""
        self.model_name = "ProsusAI/finbert"
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            self.model.to(self.device)
            self.model.eval()
            self.available = True
            print("✓ FinBert model loaded successfully")
        except Exception as e:
            self.available = False
            print(f"⚠ FinBert not available: {e}. Using fallback keyword matching.")
    
    def analyze_sentiment(self, text: str) -> Dict:
        """
        Analyze sentiment of financial text using FinBert
        
        Returns:
            {
                'sentiment': 'positive' | 'negative' | 'neutral',
                'score': float (-1 to 1),
                'confidence': float (0 to 1),
                'label_scores': dict with all labels
            }
        """
        if not self.available:
            return self._fallback_sentiment(text)
        
        try:
            # Truncate text to 512 tokens (FinBert limit)
            inputs = self.tokenizer(
                text, 
                return_tensors="pt", 
                padding=True, 
                truncation=True, 
                max_length=512
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits
                probabilities = torch.nn.functional.softmax(logits, dim=-1)
            
            # FinBert labels: 0=negative, 1=neutral, 2=positive
            label_map = {0: 'negative', 1: 'neutral', 2: 'positive'}
            predicted_class = torch.argmax(probabilities, dim=-1).item()
            predicted_sentiment = label_map[predicted_class]
            
            # Get confidence for predicted class
            confidence = float(probabilities[0, predicted_class].cpu().detach().numpy())
            
            # Convert to -1 to 1 scale
            scores = probabilities[0].cpu().detach().numpy()
            sentiment_score = float((scores[2] - scores[0]))  # positive - negative
            
            return {
                'sentiment': predicted_sentiment,
                'score': sentiment_score,
                'confidence': confidence,
                'label_scores': {
                    'negative': float(scores[0]),
                    'neutral': float(scores[1]),
                    'positive': float(scores[2])
                }
            }
        
        except Exception as e:
            print(f"Error in FinBert analysis: {e}")
            return self._fallback_sentiment(text)
    
    def analyze_multiple(self, texts: List[str]) -> List[Dict]:
        """Analyze sentiment for multiple texts"""
        return [self.analyze_sentiment(text) for text in texts]
    
    def _fallback_sentiment(self, text: str) -> Dict:
        """
        Fallback keyword-based sentiment if FinBert unavailable
        Simple but fast
        """
        text_lower = text.lower()
        
        positive_keywords = [
            'beat', 'surge', 'soar', 'jump', 'gain', 'raised', 'strong',
            'profit', 'growth', 'exceeds', 'outperforms', 'bullish',
            'approval', 'deal', 'acquisition', 'positive', 'upbeat'
        ]
        
        negative_keywords = [
            'miss', 'drop', 'fall', 'plunge', 'loss', 'cut', 'weak',
            'decline', 'falls', 'disappoints', 'bearish', 'lawsuit',
            'scandal', 'recall', 'negative', 'worst', 'penalty'
        ]
        
        positive_count = sum(1 for word in positive_keywords if word in text_lower)
        negative_count = sum(1 for word in negative_keywords if word in text_lower)
        
        if positive_count > negative_count:
            sentiment = 'positive'
        elif negative_count > positive_count:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        
        # Rough confidence based on keyword matches
        total_matches = positive_count + negative_count
        confidence = min(0.9, (total_matches / 5.0))
        
        score = (positive_count - negative_count) / max(1, (positive_count + negative_count))
        
        return {
            'sentiment': sentiment,
            'score': score,
            'confidence': confidence,
            'label_scores': {
                'negative': 0.3 if sentiment == 'negative' else 0.1,
                'neutral': 0.5 if sentiment == 'neutral' else 0.2,
                'positive': 0.3 if sentiment == 'positive' else 0.1
            },
            'method': 'fallback_keyword'
        }


# Singleton instance
_analyzer = None

def get_analyzer() -> FinBertSentimentAnalyzer:
    """Get or create FinBert analyzer instance"""
    global _analyzer
    if _analyzer is None:
        _analyzer = FinBertSentimentAnalyzer()
    return _analyzer


def analyze_headline(headline: str) -> Dict:
    """Quick function to analyze a single headline"""
    analyzer = get_analyzer()
    return analyzer.analyze_sentiment(headline)


def analyze_stock_sentiment(stock_symbol: str, stock_name: str) -> Dict:
    """
    Directly query FinBert for sentiment about a specific stock.
    
    Creates financial prompts about the stock and analyzes them with FinBert
    to get a direct sentiment score independent of headlines.
    
    Args:
        stock_symbol: e.g., "NVDA", "MSFT"
        stock_name: e.g., "NVIDIA", "Microsoft"
    
    Returns:
        {
            'stock': stock_symbol,
            'sentiment': 'positive' | 'negative' | 'neutral',
            'score': float (-1 to 1),
            'confidence': float (0 to 1),
            'source': 'direct_finbert_query'
        }
    """
    analyzer = get_analyzer()
    
    # Create stock-specific financial context prompts (fact-based for FinBert)
    # Use neutral/balanced prompts that reflect typical stock characteristics
    prompts = [
        f"{stock_name} stock trading with investor interest and market activity",
        f"{stock_name} recent quarterly results and financial performance",
        f"{stock_name} market position within competitive industry landscape"
    ]
    
    # Analyze all prompts
    results = analyzer.analyze_multiple(prompts)
    
    # Aggregate results
    total_score = 0
    total_confidence = 0
    total_positive = 0
    total_negative = 0
    total_neutral = 0
    
    for result in results:
        total_score += result['score']
        total_confidence += result['confidence']
        if result['sentiment'] == 'positive':
            total_positive += 1
        elif result['sentiment'] == 'negative':
            total_negative += 1
        else:
            total_neutral += 1
    
    # Average the scores
    avg_score = total_score / len(prompts)
    avg_confidence = total_confidence / len(prompts)
    
    # Determine overall sentiment based on majority
    if total_positive > total_negative:
        sentiment = 'positive'
    elif total_negative > total_positive:
        sentiment = 'negative'
    else:
        sentiment = 'neutral'
    
    return {
        'stock': stock_symbol,
        'sentiment': sentiment,
        'score': round(avg_score, 3),
        'confidence': round(avg_confidence, 3),
        'source': 'direct_finbert_query',
        'breakdown': {
            'positive_prompts': total_positive,
            'negative_prompts': total_negative,
            'neutral_prompts': total_neutral,
            'avg_confidence': round(avg_confidence, 3)
        }
    }


if __name__ == '__main__':
    # Test FinBert
    analyzer = FinBertSentimentAnalyzer()
    
    test_headlines = [
        "NVDA beats earnings expectations with strong guidance",
        "Tesla faces significant lawsuit from regulators",
        "Apple announces new product line, stock unchanged",
        "Fed raises interest rates more than expected",
        "Microsoft reports record profits and revenue growth",
    ]
    
    print("\n🧠 FINBERT SENTIMENT ANALYSIS TEST")
    print("="*70)
    
    for headline in test_headlines:
        result = analyzer.analyze_sentiment(headline)
        
        sentiment = result['sentiment'].upper()
        score = result['score']
        confidence = result['confidence']
        
        print(f"\nHeadline: {headline}")
        print(f"  Sentiment: {sentiment} (score: {score:+.2f}, confidence: {confidence:.1%})")
        print(f"  Breakdown: Positive {result['label_scores']['positive']:.1%} | "
              f"Neutral {result['label_scores']['neutral']:.1%} | "
              f"Negative {result['label_scores']['negative']:.1%}")
