"""
Portfolio Management System - Data Layer
Handles storage and retrieval of portfolios and positions using SQLite.
"""

import sqlite3
import uuid
from datetime import datetime
from typing import List, Dict, Optional
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'portfolios.db')

class PortfolioManager:
    def __init__(self):
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Create database and tables if they don't exist."""
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Portfolios table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolios (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                cash_usd REAL DEFAULT 100000.0,
                cash_cad REAL DEFAULT 0.0,
                initial_balance REAL DEFAULT 100000.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Positions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id TEXT PRIMARY KEY,
                portfolio_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                quantity REAL NOT NULL,
                avg_cost REAL NOT NULL,
                purchase_date TIMESTAMP,
                notes TEXT,
                category TEXT DEFAULT 'Stock',
                currency TEXT DEFAULT 'USD',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE
            )
        ''')

        # Trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                portfolio_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                type TEXT NOT NULL, -- BUY/SELL
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                currency TEXT DEFAULT 'USD',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE
            )
        ''')
        
        # Migrations
        try:
            cursor.execute('ALTER TABLE portfolios ADD COLUMN cash_usd REAL DEFAULT 100000.0')
            cursor.execute('ALTER TABLE portfolios ADD COLUMN cash_cad REAL DEFAULT 0.0')
            cursor.execute('ALTER TABLE portfolios ADD COLUMN initial_balance REAL DEFAULT 100000.0')
        except sqlite3.OperationalError:
            pass # Columns likely exist

        try:
            cursor.execute('ALTER TABLE positions ADD COLUMN category TEXT DEFAULT "Stock"')
        except sqlite3.OperationalError:
            pass # Column likely exists

        try:
            cursor.execute('ALTER TABLE positions ADD COLUMN currency TEXT DEFAULT "USD"')
        except sqlite3.OperationalError:
            pass # Column likely exists
        
        # Create indexes for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_portfolio ON positions(portfolio_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_portfolio ON trades(portfolio_id)')
        
        conn.commit()
        conn.close()
    
    def create_portfolio(self, name: str, description: str = "", balance: float = 100000.0) -> Dict:
        """Create a new portfolio with a starting balance."""
        portfolio_id = str(uuid.uuid4())
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO portfolios (id, name, description, cash_usd, initial_balance)
            VALUES (?, ?, ?, ?, ?)
        ''', (portfolio_id, name, description, balance, balance))
        
        conn.commit()
        conn.close()
        
        return {
            "id": portfolio_id,
            "name": name,
            "description": description,
            "cash_usd": balance,
            "initial_balance": balance,
            "created_at": datetime.now().isoformat()
        }
    
    def list_portfolios(self) -> List[Dict]:
        """Get all portfolios with position counts and balances."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                p.id,
                p.name,
                p.description,
                p.cash_usd,
                p.cash_cad,
                p.initial_balance,
                p.created_at,
                p.updated_at,
                COUNT(pos.id) as position_count
            FROM portfolios p
            LEFT JOIN positions pos ON p.id = pos.portfolio_id
            GROUP BY p.id
            ORDER BY p.created_at DESC
        ''')
        
        portfolios = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return portfolios
    
    def get_portfolio(self, portfolio_id: str) -> Optional[Dict]:
        """Get a single portfolio with all positions and balances."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get portfolio
        cursor.execute('SELECT * FROM portfolios WHERE id = ?', (portfolio_id,))
        portfolio = cursor.fetchone()
        
        if not portfolio:
            conn.close()
            return None
        
        portfolio_dict = dict(portfolio)
        
        # Get positions
        cursor.execute('''
            SELECT * FROM positions 
            WHERE portfolio_id = ?
            ORDER BY created_at DESC
        ''', (portfolio_id,))
        
        positions = [dict(row) for row in cursor.fetchall()]
        portfolio_dict['positions'] = positions
        
        conn.close()
        return portfolio_dict
    
    def update_portfolio(self, portfolio_id: str, name: Optional[str] = None, description: Optional[str] = None) -> bool:
        """Update portfolio metadata."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        
        if not updates:
            conn.close()
            return False
        
        params.append(portfolio_id)
        
        query = f"UPDATE portfolios SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        cursor.execute(query, params)
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
    
    def delete_portfolio(self, portfolio_id: str) -> bool:
        """Delete a portfolio and all its positions."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM portfolios WHERE id = ?', (portfolio_id,))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
    
    def execute_trade(self, portfolio_id: str, ticker: str, trade_type: str, 
                      quantity: float, price: float, currency: str = "USD", notes: str = "") -> Dict:
        """
        Executes a paper trade:
        1. Validates funds if buying.
        2. Updates cash balance.
        3. Updates or creates position.
        4. Logs to trade history.
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        ticker = ticker.upper()
        trade_type = trade_type.upper()
        total_cost = quantity * price
        
        # 1. Get current balance
        balance_col = "cash_usd" if currency == "USD" else "cash_cad"
        cursor.execute(f"SELECT {balance_col} FROM portfolios WHERE id = ?", (portfolio_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return {"error": "Portfolio not found"}
            
        current_balance = row[0]
        
        if trade_type == "BUY" and current_balance < total_cost:
            conn.close()
            return {"error": "Insufficient funds"}
            
        # 2. Update Cash
        new_balance = current_balance - total_cost if trade_type == "BUY" else current_balance + total_cost
        cursor.execute(f"UPDATE portfolios SET {balance_col} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_balance, portfolio_id))
        
        # 3. Handle Position
        cursor.execute("SELECT id, quantity, avg_cost FROM positions WHERE portfolio_id = ? AND ticker = ?", (portfolio_id, ticker))
        pos_row = cursor.fetchone()
        
        if trade_type == "BUY":
            if pos_row:
                pos_id, cur_qty, cur_avg = pos_row
                new_qty = cur_qty + quantity
                new_avg = ((cur_qty * cur_avg) + total_cost) / new_qty
                cursor.execute("UPDATE positions SET quantity = ?, avg_cost = ? WHERE id = ?", (new_qty, new_avg, pos_id))
            else:
                pos_id = str(uuid.uuid4())
                cursor.execute('''
                    INSERT INTO positions (id, portfolio_id, ticker, quantity, avg_cost, currency, category)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (pos_id, portfolio_id, ticker, quantity, price, currency, 'Stock'))
        else: # SELL
            if not pos_row or pos_row[1] < quantity:
                conn.close()
                return {"error": "Insufficient shares to sell"}
            
            pos_id, cur_qty, cur_avg = pos_row
            new_qty = cur_qty - quantity
            if new_qty <= 0:
                cursor.execute("DELETE FROM positions WHERE id = ?", (pos_id,))
            else:
                cursor.execute("UPDATE positions SET quantity = ? WHERE id = ?", (new_qty, pos_id))
        
        # 4. Log Trade
        trade_id = str(uuid.uuid4())
        cursor.execute('''
            INSERT INTO trades (id, portfolio_id, ticker, type, quantity, price, currency, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (trade_id, portfolio_id, ticker, trade_type, quantity, price, currency, notes))
        
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "trade_id": trade_id,
            "new_balance": new_balance,
            "currency": currency
        }

    def get_trade_history(self, portfolio_id: str) -> List[Dict]:
        """Fetch trade history for a portfolio."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM trades 
            WHERE portfolio_id = ?
            ORDER BY timestamp DESC
        ''', (portfolio_id,))
        
        trades = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return trades

    def reset_portfolio(self, portfolio_id: str) -> bool:
        """Resets portfolio to initial balance and removes all positions/trades."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT initial_balance FROM portfolios WHERE id = ?", (portfolio_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False
            
        initial = row[0]
        cursor.execute("UPDATE portfolios SET cash_usd = ?, cash_cad = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (initial, portfolio_id))
        cursor.execute("DELETE FROM positions WHERE portfolio_id = ?", (portfolio_id,))
        cursor.execute("DELETE FROM trades WHERE portfolio_id = ?", (portfolio_id,))
        
        conn.commit()
        conn.close()
        return True

    def add_position(self, portfolio_id: str, ticker: str, quantity: float, 
                      avg_cost: float, purchase_date: Optional[str] = None, notes: str = "", category: str = "Stock") -> Dict:
        """Add a position to a portfolio (Legacy support)."""
        position_id = str(uuid.uuid4())
        
        if purchase_date is None:
            purchase_date = datetime.now().isoformat()
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO positions (id, portfolio_id, ticker, quantity, avg_cost, purchase_date, notes, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (position_id, portfolio_id, ticker.upper(), quantity, avg_cost, purchase_date, notes, category))
        
        # Update portfolio updated_at
        cursor.execute('UPDATE portfolios SET updated_at = CURRENT_TIMESTAMP WHERE id = ?', (portfolio_id,))
        
        conn.commit()
        conn.close()
        
        return {
            "id": position_id,
            "portfolio_id": portfolio_id,
            "ticker": ticker.upper(),
            "quantity": quantity,
            "avg_cost": avg_cost,
            "purchase_date": purchase_date,
            "notes": notes,
            "category": category
        }
    
    def update_position(self, position_id: str, quantity: Optional[float] = None, 
                       avg_cost: Optional[float] = None, notes: Optional[str] = None) -> bool:
        """Update a position."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if quantity is not None:
            updates.append("quantity = ?")
            params.append(quantity)
        
        if avg_cost is not None:
            updates.append("avg_cost = ?")
            params.append(avg_cost)
        
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        
        if not updates:
            conn.close()
            return False
        
        params.append(position_id)
        
        query = f"UPDATE positions SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, params)
        
        # Update parent portfolio
        cursor.execute('''
            UPDATE portfolios 
            SET updated_at = CURRENT_TIMESTAMP 
            WHERE id = (SELECT portfolio_id FROM positions WHERE id = ?)
        ''', (position_id,))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
    
    def delete_position(self, position_id: str) -> bool:
        """Delete a position."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get portfolio_id before deleting
        cursor.execute('SELECT portfolio_id FROM positions WHERE id = ?', (position_id,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return False
        
        portfolio_id = result[0]
        
        cursor.execute('DELETE FROM positions WHERE id = ?', (position_id,))
        
        # Update parent portfolio
        cursor.execute('UPDATE portfolios SET updated_at = CURRENT_TIMESTAMP WHERE id = ?', (portfolio_id,))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
    
    def get_all_tickers(self, portfolio_id: str) -> List[str]:
        """Get all unique tickers in a portfolio."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT DISTINCT ticker 
            FROM positions 
            WHERE portfolio_id = ?
        ''', (portfolio_id,))
        
        tickers = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        return tickers


if __name__ == "__main__":
    # Test the portfolio manager
    pm = PortfolioManager()
    
    # Create a test portfolio
    portfolio = pm.create_portfolio("Test Portfolio", "My first portfolio")
    print(f"Created portfolio: {portfolio}")
    
    # Add some positions
    pos1 = pm.add_position(portfolio['id'], "AAPL", 10, 150.00, notes="Initial buy")
    pos2 = pm.add_position(portfolio['id'], "MSFT", 5, 300.00)
    print(f"Added positions: {pos1}, {pos2}")
    
    # List portfolios
    portfolios = pm.list_portfolios()
    print(f"All portfolios: {portfolios}")
    
    # Get portfolio with positions
    full_portfolio = pm.get_portfolio(portfolio['id'])
    print(f"Full portfolio: {full_portfolio}")
