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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE
            )
        ''')
        
        # Migration: Add category column if missing
        try:
            cursor.execute('ALTER TABLE positions ADD COLUMN category TEXT DEFAULT "Stock"')
        except sqlite3.OperationalError:
            pass # Column likely exists
        
        # Create indexes for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_portfolio ON positions(portfolio_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker)')
        
        conn.commit()
        conn.close()
    
    def create_portfolio(self, name: str, description: str = "") -> Dict:
        """Create a new portfolio."""
        portfolio_id = str(uuid.uuid4())
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO portfolios (id, name, description)
            VALUES (?, ?, ?)
        ''', (portfolio_id, name, description))
        
        conn.commit()
        conn.close()
        
        return {
            "id": portfolio_id,
            "name": name,
            "description": description,
            "created_at": datetime.now().isoformat()
        }
    
    def list_portfolios(self) -> List[Dict]:
        """Get all portfolios with position counts."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                p.id,
                p.name,
                p.description,
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
        """Get a single portfolio with all positions."""
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
    
    def update_portfolio(self, portfolio_id: str, name: str = None, description: str = None) -> bool:
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
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(portfolio_id)
        
        query = f"UPDATE portfolios SET {', '.join(updates)} WHERE id = ?"
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
    
    def add_position(self, portfolio_id: str, ticker: str, quantity: float, 
                     avg_cost: float, purchase_date: str = None, notes: str = "", category: str = "Stock") -> Dict:
        """Add a position to a portfolio."""
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
    
    def update_position(self, position_id: str, quantity: float = None, 
                       avg_cost: float = None, notes: str = None) -> bool:
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
