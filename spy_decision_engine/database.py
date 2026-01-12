"""
SQLite Database for storing engine runs, trades, and analysis results
Lightweight, no external dependencies, persists to local file
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

class DecisionDatabase:
    """Manage all decision engine, trade, and analysis data"""
    
    def __init__(self, db_path: str = None):
        """Initialize database"""
        if db_path is None:
            db_path = Path(__file__).parent / 'data' / 'spy_trading.db'
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create tables if they don't exist
        self._init_tables()
    
    def _get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_tables(self):
        """Create tables if they don't exist"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Table 1: Engine runs (daily decisions)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS engine_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date TEXT NOT NULL,
                run_time TEXT NOT NULL,
                timestamp TEXT NOT NULL UNIQUE,
                decision TEXT,
                final_score REAL,
                confidence REAL,
                spy_price REAL,
                recommended_entry REAL,
                take_profit REAL,
                stop_loss REAL,
                direction TEXT,
                components_json TEXT,
                full_report_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table 2: Trades
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT NOT NULL UNIQUE,
                entry_date TEXT,
                entry_time TEXT,
                exit_date TEXT,
                exit_time TEXT,
                instrument TEXT,
                strike REAL,
                dte INTEGER,
                direction TEXT,
                entry_price REAL,
                premium_paid REAL,
                contracts INTEGER,
                engine_confidence REAL,
                exit_price REAL,
                premium_sold REAL,
                profit REAL,
                profit_pct REAL,
                is_open INTEGER DEFAULT 1,
                reason TEXT,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                closed_at TEXT
            )
        ''')
        
        # Table 3: Analysis results
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analysis_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_date TEXT NOT NULL,
                analysis_type TEXT,
                total_trades INTEGER,
                wins INTEGER,
                losses INTEGER,
                win_rate REAL,
                net_profit REAL,
                avg_profit_per_trade REAL,
                profit_factor REAL,
                best_entry_price TEXT,
                best_dte TEXT,
                best_confidence_threshold REAL,
                prediction_accuracy REAL,
                recommendations_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table 4: Daily performance summary
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL UNIQUE,
                trades_entered INTEGER,
                trades_closed INTEGER,
                daily_profit REAL,
                daily_trades_win_rate REAL,
                engine_decision TEXT,
                engine_confidence REAL,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    # ==================== ENGINE RUNS ====================
    
    def save_engine_run(self, decision_dict: Dict) -> int:
        """Save engine run to database"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Extract data
        timestamp = decision_dict.get('timestamp', datetime.now().strftime('%H:%M'))
        run_date = datetime.now().strftime('%Y-%m-%d')
        run_time = timestamp
        
        entry_strategy = decision_dict.get('entry_strategy', {})
        risk_reward = decision_dict.get('risk_reward', {})
        market_conditions = decision_dict.get('market_conditions', {})
        
        try:
            cursor.execute('''
                INSERT INTO engine_runs (
                    run_date, run_time, timestamp,
                    decision, final_score, confidence,
                    spy_price, recommended_entry, take_profit, stop_loss,
                    direction, components_json, full_report_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                run_date,
                run_time,
                f"{run_date} {run_time}",
                decision_dict.get('decision'),
                decision_dict.get('final_score'),
                decision_dict.get('final_score'),  # Use final_score as confidence
                market_conditions.get('spy_price'),
                entry_strategy.get('recommended_entry'),
                risk_reward.get('take_profit_target'),
                risk_reward.get('stop_loss_level'),
                'UP' if 'BUY' in decision_dict.get('decision', '') else 'DOWN',
                json.dumps(decision_dict.get('component_scores', {})),
                json.dumps(decision_dict)
            ))
            
            conn.commit()
            run_id = cursor.lastrowid
            return run_id
        
        except sqlite3.IntegrityError:
            # Duplicate timestamp, update instead
            cursor.execute('''
                UPDATE engine_runs SET full_report_json = ? 
                WHERE timestamp = ?
            ''', (json.dumps(decision_dict), f"{run_date} {run_time}"))
            conn.commit()
            return None
        
        finally:
            conn.close()
    
    def get_latest_run(self) -> Optional[Dict]:
        """Get most recent engine run"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM engine_runs 
            ORDER BY created_at DESC 
            LIMIT 1
        ''')
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def get_runs_by_date(self, date: str) -> List[Dict]:
        """Get all runs for a specific date"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM engine_runs 
            WHERE run_date = ?
            ORDER BY run_time DESC
        ''', (date,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_all_runs(self, limit: int = 100) -> List[Dict]:
        """Get recent engine runs"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM engine_runs 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    # ==================== TRADES ====================
    
    def add_trade(self, trade_data: Dict) -> str:
        """Add trade to database"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        trade_id = trade_data.get('id', f"{datetime.now().strftime('%Y-%m-%d-%H%M%S')}")
        entry_date = trade_data.get('entry_date', datetime.now().strftime('%Y-%m-%d'))
        entry_time = trade_data.get('entry_time', datetime.now().strftime('%H:%M'))
        
        try:
            cursor.execute('''
                INSERT INTO trades (
                    trade_id, entry_date, entry_time,
                    instrument, strike, dte, direction,
                    entry_price, premium_paid, contracts,
                    engine_confidence, reason, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade_id,
                entry_date,
                entry_time,
                trade_data.get('instrument'),
                trade_data.get('strike'),
                trade_data.get('dte'),
                trade_data.get('direction'),
                trade_data.get('entry_price'),
                trade_data.get('premium_paid'),
                trade_data.get('contracts'),
                trade_data.get('engine_confidence'),
                trade_data.get('reason'),
                trade_data.get('notes')
            ))
            
            conn.commit()
            return trade_id
        
        finally:
            conn.close()
    
    def close_trade(self, trade_id: str, exit_data: Dict) -> bool:
        """Close a trade (record exit)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        exit_date = exit_data.get('exit_date', datetime.now().strftime('%Y-%m-%d'))
        exit_time = exit_data.get('exit_time', datetime.now().strftime('%H:%M'))
        exit_price = exit_data.get('exit_price')
        premium_sold = exit_data.get('premium_sold')
        
        # Get entry to calculate P&L
        cursor.execute('SELECT * FROM trades WHERE trade_id = ?', (trade_id,))
        trade = cursor.fetchone()
        
        if not trade:
            conn.close()
            return False
        
        # Calculate profit
        profit = (premium_sold - trade['premium_paid']) * trade['contracts'] * 100 if premium_sold else 0
        profit_pct = ((premium_sold - trade['premium_paid']) / trade['premium_paid'] * 100) if premium_sold else 0
        
        try:
            cursor.execute('''
                UPDATE trades SET
                    exit_date = ?, exit_time = ?,
                    exit_price = ?, premium_sold = ?,
                    profit = ?, profit_pct = ?,
                    is_open = 0, closed_at = CURRENT_TIMESTAMP
                WHERE trade_id = ?
            ''', (
                exit_date, exit_time, exit_price, premium_sold,
                profit, profit_pct, trade_id
            ))
            
            conn.commit()
            return True
        
        finally:
            conn.close()
    
    def get_trade(self, trade_id: str) -> Optional[Dict]:
        """Get specific trade"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM trades WHERE trade_id = ?', (trade_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_open_trades(self) -> List[Dict]:
        """Get all open trades"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM trades 
            WHERE is_open = 1
            ORDER BY created_at DESC
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_closed_trades(self) -> List[Dict]:
        """Get all closed trades"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM trades 
            WHERE is_open = 0
            ORDER BY closed_at DESC
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_trades_by_date(self, date: str) -> List[Dict]:
        """Get trades for specific date"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM trades 
            WHERE entry_date = ? OR exit_date = ?
            ORDER BY created_at DESC
        ''', (date, date))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_all_trades(self, limit: int = 100) -> List[Dict]:
        """Get recent trades"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM trades 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    # ==================== ANALYSIS ====================
    
    def save_analysis(self, analysis_data: Dict) -> int:
        """Save analysis results to database"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        analysis_date = datetime.now().strftime('%Y-%m-%d')
        
        try:
            cursor.execute('''
                INSERT INTO analysis_results (
                    analysis_date, analysis_type,
                    total_trades, wins, losses, win_rate,
                    net_profit, avg_profit_per_trade, profit_factor,
                    best_entry_price, best_dte, best_confidence_threshold,
                    prediction_accuracy, recommendations_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                analysis_date,
                analysis_data.get('type', 'daily'),
                analysis_data.get('total_trades'),
                analysis_data.get('wins'),
                analysis_data.get('losses'),
                analysis_data.get('win_rate'),
                analysis_data.get('net_profit'),
                analysis_data.get('avg_profit_per_trade'),
                analysis_data.get('profit_factor'),
                json.dumps(analysis_data.get('best_entry_price')),
                json.dumps(analysis_data.get('best_dte')),
                analysis_data.get('best_confidence_threshold'),
                analysis_data.get('prediction_accuracy'),
                json.dumps(analysis_data.get('recommendations', {}))
            ))
            
            conn.commit()
            return cursor.lastrowid
        
        finally:
            conn.close()
    
    def get_latest_analysis(self) -> Optional[Dict]:
        """Get most recent analysis"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM analysis_results 
            ORDER BY created_at DESC 
            LIMIT 1
        ''')
        
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_analysis_by_date(self, date: str) -> Optional[Dict]:
        """Get analysis for specific date"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM analysis_results 
            WHERE analysis_date = ?
            ORDER BY created_at DESC 
            LIMIT 1
        ''', (date,))
        
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_all_analysis(self, limit: int = 100) -> List[Dict]:
        """Get recent analysis results"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM analysis_results 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    # ==================== DAILY PERFORMANCE ====================
    
    def save_daily_performance(self, date: str, perf_data: Dict) -> int:
        """Save daily performance summary"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO daily_performance (
                    trade_date, trades_entered, trades_closed,
                    daily_profit, daily_trades_win_rate,
                    engine_decision, engine_confidence, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                date,
                perf_data.get('trades_entered'),
                perf_data.get('trades_closed'),
                perf_data.get('daily_profit'),
                perf_data.get('daily_trades_win_rate'),
                perf_data.get('engine_decision'),
                perf_data.get('engine_confidence'),
                perf_data.get('notes')
            ))
            
            conn.commit()
            return cursor.lastrowid
        
        finally:
            conn.close()
    
    def get_daily_performance(self, date: str) -> Optional[Dict]:
        """Get daily performance for specific date"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM daily_performance 
            WHERE trade_date = ?
        ''', (date,))
        
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_performance_range(self, start_date: str, end_date: str) -> List[Dict]:
        """Get performance data for date range"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM daily_performance 
            WHERE trade_date BETWEEN ? AND ?
            ORDER BY trade_date DESC
        ''', (start_date, end_date))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    # ==================== STATISTICS ====================
    
    def get_trade_stats(self) -> Dict:
        """Calculate overall trade statistics"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN profit = 0 THEN 1 ELSE 0 END) as breaks,
                SUM(profit) as net_profit,
                AVG(profit) as avg_profit,
                SUM(CASE WHEN profit > 0 THEN profit ELSE 0 END) as total_wins_profit,
                SUM(CASE WHEN profit < 0 THEN ABS(profit) ELSE 0 END) as total_losses,
                AVG(profit_pct) as avg_roi
            FROM trades 
            WHERE is_open = 0
        ''')
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return {}
        
        stats = dict(row)
        
        # Handle None values
        total_trades = stats['total_trades'] or 0
        total_losses = stats['total_losses'] or 0
        total_wins_profit = stats['total_wins_profit'] or 0
        
        stats['win_rate'] = (stats['wins'] / total_trades * 100) if total_trades > 0 else 0
        stats['profit_factor'] = (total_wins_profit / total_losses) if total_losses > 0 else 0
        
        return stats
    
    def get_win_rate_by_strike(self) -> Dict:
        """Get win rate by strike price"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                strike,
                COUNT(*) as total,
                SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
                SUM(profit) as total_profit,
                AVG(profit_pct) as avg_roi
            FROM trades 
            WHERE is_open = 0
            GROUP BY strike
            ORDER BY win_rate DESC
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_win_rate_by_dte(self) -> Dict:
        """Get win rate by DTE"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                dte,
                COUNT(*) as total,
                SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
                SUM(profit) as total_profit,
                AVG(profit_pct) as avg_roi
            FROM trades 
            WHERE is_open = 0
            GROUP BY dte
            ORDER BY dte
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_win_rate_by_confidence(self) -> Dict:
        """Get win rate by engine confidence level"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                CASE 
                    WHEN engine_confidence >= 80 THEN '80-100%'
                    WHEN engine_confidence >= 70 THEN '70-80%'
                    WHEN engine_confidence >= 60 THEN '60-70%'
                    ELSE '<60%'
                END as confidence_range,
                COUNT(*) as total,
                SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as wins,
                SUM(profit) as total_profit,
                AVG(profit_pct) as avg_roi
            FROM trades 
            WHERE is_open = 0
            GROUP BY confidence_range
            ORDER BY confidence_range DESC
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def export_to_json(self, filepath: str = None) -> str:
        """Export all data to JSON for backup/analysis"""
        if filepath is None:
            filepath = Path(self.db_path).parent / f"spy_trading_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        data = {
            'timestamp': datetime.now().isoformat(),
            'engine_runs': self.get_all_runs(limit=1000),
            'trades': self.get_all_trades(limit=1000),
            'analysis': self.get_all_analysis(limit=100),
            'stats': self.get_trade_stats(),
            'stats_by_strike': self.get_win_rate_by_strike(),
            'stats_by_dte': self.get_win_rate_by_dte(),
            'stats_by_confidence': self.get_win_rate_by_confidence()
        }
        
        # Convert sqlite3.Row objects to dict
        def convert_rows(obj):
            if isinstance(obj, dict):
                return {k: convert_rows(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [convert_rows(item) for item in obj]
            else:
                return obj
        
        data = convert_rows(data)
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        return str(filepath)


# Convenience function
def get_db(db_path: str = None) -> DecisionDatabase:
    """Get database instance"""
    return DecisionDatabase(db_path)


if __name__ == '__main__':
    # Test the database
    db = DecisionDatabase()
    
    print("Database initialized at:", db.db_path)
    print("Tables created successfully!")
    
    # Show stats if any trades exist
    stats = db.get_trade_stats()
    if stats.get('total_trades', 0) > 0:
        print(f"\nCurrent Stats:")
        print(f"  Total Trades: {stats['total_trades']}")
        print(f"  Win Rate: {stats['win_rate']:.1f}%")
        print(f"  Net Profit: ${stats['net_profit']:.2f}")
