"""
Trade Tracker Module

Records all trades (entries/exits) for historical analysis and learning.
Helps identify which price levels, DTEs, and conditions work best.
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TradeTracker:
    """Records and manages trade history for learning and analysis."""
    
    def __init__(self, trades_file: str = "spy_decision_engine/data/trades.json"):
        """
        Initialize trade tracker.
        
        Args:
            trades_file: Path to trades history JSON file
        """
        self.trades_file = trades_file
        self.trades = self._load_trades()
    
    def _load_trades(self) -> Dict:
        """Load trades from file or create new structure."""
        if os.path.exists(self.trades_file):
            with open(self.trades_file, 'r') as f:
                return json.load(f)
        
        # Create new trades structure
        return {
            "trades": [],
            "summary": {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_profit": 0,
                "total_loss": 0,
                "avg_profit_per_trade": 0.0,
                "largest_win": 0,
                "largest_loss": 0,
                "profit_factor": 0.0,
            }
        }
    
    def add_trade(self, 
                 instrument: str,
                 strike: int,
                 expiry_dte: int,
                 entry_price: float,
                 entry_time: str,
                 premium_paid: float,
                 contracts: int,
                 engine_confidence: float,
                 engine_recommendation: str,
                 exit_price: Optional[float] = None,
                 exit_time: Optional[str] = None,
                 premium_sold: Optional[float] = None,
                 reason_for_entry: str = "",
                 predicted_direction: str = "") -> str:
        """
        Add a trade entry.
        
        Args:
            instrument: "SPY Call" or "SPY Put"
            strike: Strike price
            expiry_dte: Days to expiry (1, 2, 3, or 4)
            entry_price: SPY price at entry
            entry_time: Time of entry (HH:MM format)
            premium_paid: Premium paid per contract
            contracts: Number of contracts
            engine_confidence: Engine's confidence score (0-100)
            engine_recommendation: Engine's recommendation
            exit_price: SPY price at exit (optional, for open trades)
            exit_time: Time of exit (optional)
            premium_sold: Premium received at exit (optional)
            reason_for_entry: Why you entered this trade
            predicted_direction: Predicted price direction (UP/DOWN)
        
        Returns:
            Trade ID
        """
        trade_id = f"{datetime.now().strftime('%Y-%m-%d')}-{len(self.trades['trades']) + 1:03d}"
        
        trade = {
            "trade_id": trade_id,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "instrument": instrument,
            "strike": strike,
            "expiry_dte": expiry_dte,
            "entry": {
                "price": entry_price,
                "time": entry_time,
                "premium_paid": premium_paid,
                "contracts": contracts,
                "total_cost": premium_paid * contracts * 100,  # Options are $1 per contract in cents
                "engine_confidence": engine_confidence,
                "engine_recommendation": engine_recommendation,
                "predicted_direction": predicted_direction,
                "reason": reason_for_entry,
            },
            "exit": None,
            "analysis": None
        }
        
        if exit_price and exit_time and premium_sold:
            trade["exit"] = {
                "price": exit_price,
                "time": exit_time,
                "premium_sold": premium_sold,
                "proceeds": premium_sold * contracts * 100,
                "profit": (premium_sold - premium_paid) * contracts * 100,
                "profit_pct": ((premium_sold - premium_paid) / premium_paid) * 100,
                "reason": ""  # You provide this separately
            }
            
            # Auto-calculate analysis
            trade["analysis"] = self._analyze_trade(trade, entry_price, exit_price)
        
        self.trades["trades"].append(trade)
        self._save_trades()
        logger.info(f"Trade {trade_id} added successfully")
        
        return trade_id
    
    def close_trade(self,
                   trade_id: str,
                   exit_price: float,
                   exit_time: str,
                   premium_sold: float,
                   reason_for_exit: str = "") -> bool:
        """
        Close an open trade with exit details.
        
        Args:
            trade_id: ID of trade to close
            exit_price: SPY price at exit
            exit_time: Time of exit
            premium_sold: Premium received at exit
            reason_for_exit: Why you exited
        
        Returns:
            True if successful
        """
        for trade in self.trades["trades"]:
            if trade["trade_id"] == trade_id and trade["exit"] is None:
                contracts = trade["entry"]["contracts"]
                premium_paid = trade["entry"]["premium_paid"]
                
                trade["exit"] = {
                    "price": exit_price,
                    "time": exit_time,
                    "premium_sold": premium_sold,
                    "proceeds": premium_sold * contracts * 100,
                    "profit": (premium_sold - premium_paid) * contracts * 100,
                    "profit_pct": ((premium_sold - premium_paid) / premium_paid) * 100,
                    "reason": reason_for_exit
                }
                
                # Analyze the closed trade
                entry_price = trade["entry"]["price"]
                trade["analysis"] = self._analyze_trade(trade, entry_price, exit_price)
                
                self._save_trades()
                self._update_summary()
                logger.info(f"Trade {trade_id} closed with {trade['exit']['profit']:.2f} profit")
                return True
        
        logger.warning(f"Trade {trade_id} not found or already closed")
        return False
    
    def _analyze_trade(self, trade: Dict, entry_price: float, exit_price: float) -> Dict:
        """
        Analyze if predictions were correct.
        
        Args:
            trade: Trade dictionary
            entry_price: SPY entry price
            exit_price: SPY exit price
        
        Returns:
            Analysis dictionary
        """
        predicted_direction = trade["entry"].get("predicted_direction", "UP")
        actual_direction = "UP" if exit_price >= entry_price else "DOWN"
        prediction_correct = predicted_direction == actual_direction
        
        exit_profit = trade["exit"]["profit"] if trade["exit"] else 0
        
        return {
            "predicted_direction": predicted_direction,
            "actual_direction": actual_direction,
            "prediction_correct": prediction_correct,
            "spy_move": round(exit_price - entry_price, 2),
            "move_pct": round(((exit_price - entry_price) / entry_price) * 100, 2),
            "profit_realized": exit_profit,
            "lesson": self._generate_lesson(trade, prediction_correct, exit_price - entry_price)
        }
    
    def _generate_lesson(self, trade: Dict, correct: bool, spy_move: float) -> str:
        """Generate a lesson from the trade result."""
        confidence = trade["entry"]["engine_confidence"]
        dte = trade["expiry_dte"]
        instrument = trade["instrument"]
        
        if correct:
            if confidence > 80:
                return f"✓ High confidence trade worked. {instrument} was right. {dte} DTE was good."
            else:
                return f"✓ Low confidence trade worked anyway. Lucky? Or missed a signal?"
        else:
            if confidence > 80:
                return f"✗ High confidence prediction failed. Model needs recalibration."
            else:
                return f"✗ Low confidence trade failed as expected. Should have skipped."
    
    def _update_summary(self) -> None:
        """Update summary statistics from trades."""
        closed_trades = [t for t in self.trades["trades"] if t["exit"] is not None]
        
        if not closed_trades:
            return
        
        winning_trades = [t for t in closed_trades if t["exit"]["profit"] > 0]
        losing_trades = [t for t in closed_trades if t["exit"]["profit"] < 0]
        
        total_profit = sum(t["exit"]["profit"] for t in winning_trades)
        total_loss = sum(abs(t["exit"]["profit"]) for t in losing_trades)
        
        self.trades["summary"] = {
            "total_trades": len(closed_trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": round((len(winning_trades) / len(closed_trades)) * 100, 1) if closed_trades else 0,
            "total_profit": round(total_profit, 2),
            "total_loss": round(total_loss, 2),
            "net_profit": round(total_profit - total_loss, 2),
            "avg_profit_per_trade": round((total_profit - total_loss) / len(closed_trades), 2) if closed_trades else 0,
            "largest_win": round(max([t["exit"]["profit"] for t in winning_trades], default=0), 2),
            "largest_loss": round(min([t["exit"]["profit"] for t in losing_trades], default=0), 2),
            "profit_factor": round(total_profit / total_loss, 2) if total_loss > 0 else 0,
        }
    
    def _save_trades(self) -> None:
        """Save trades to file."""
        os.makedirs(os.path.dirname(self.trades_file), exist_ok=True)
        with open(self.trades_file, 'w') as f:
            json.dump(self.trades, f, indent=2)
    
    def get_summary(self) -> Dict:
        """Get summary statistics."""
        return self.trades["summary"]
    
    def get_trades(self, closed_only: bool = False) -> List[Dict]:
        """
        Get all trades.
        
        Args:
            closed_only: Only return closed trades
        
        Returns:
            List of trades
        """
        if closed_only:
            return [t for t in self.trades["trades"] if t["exit"] is not None]
        return self.trades["trades"]
    
    def get_open_trades(self) -> List[Dict]:
        """Get open (not yet closed) trades."""
        return [t for t in self.trades["trades"] if t["exit"] is None]
    
    def print_summary(self) -> None:
        """Print summary to console."""
        summary = self.get_summary()
        print("\n" + "=" * 60)
        print("TRADE SUMMARY")
        print("=" * 60)
        print(f"Total Trades: {summary['total_trades']}")
        print(f"Wins: {summary['winning_trades']} | Losses: {summary['losing_trades']}")
        print(f"Win Rate: {summary['win_rate']}%")
        print(f"Net Profit: ${summary['net_profit']:.2f}")
        print(f"Avg Profit/Trade: ${summary['avg_profit_per_trade']:.2f}")
        print(f"Largest Win: ${summary['largest_win']:.2f}")
        print(f"Largest Loss: ${summary['largest_loss']:.2f}")
        print(f"Profit Factor: {summary['profit_factor']}")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    # Example usage
    tracker = TradeTracker()
    
    # Add a new trade
    trade_id = tracker.add_trade(
        instrument="SPY Call",
        strike=690,
        expiry_dte=2,
        entry_price=688.69,
        entry_time="09:35",
        premium_paid=2.50,
        contracts=10,
        engine_confidence=79.9,
        engine_recommendation="BUY SMALL at support",
        predicted_direction="UP",
        reason_for_entry="Bullish momentum + positive sentiment"
    )
    
    print(f"Added trade: {trade_id}")
    
    # Later, close the trade
    tracker.close_trade(
        trade_id=trade_id,
        exit_price=692.32,
        exit_time="14:45",
        premium_sold=4.13,
        reason_for_exit="Took profit at target"
    )
    
    # Print summary
    tracker.print_summary()
