import yfinance as yf
import random

# Curated List of Futuristic Bets
# Structure: Theme -> Ticker -> metadata
MOONSHOT_THEMES = {
    "Robotics & AI": {
        "ISRG": {"name": "Intuitive Surgical", "role": "Direct", "horizon": "3y", "desc": "Market leader in robotic surgery (Da Vinci)."},
        "PATH": {"name": "UiPath", "role": "Direct", "horizon": "5y", "desc": "AI software robots automating white-collar work."},
        "NVDA": {"name": "Nvidia", "role": "Indirect", "horizon": "3y", "desc": "The brain behind every AI and robot."},
        "ROK": {"name": "Rockwell Automation", "role": "Indirect", "horizon": "3y", "desc": "Industrial automation infrastructure."},
        "BSY": {"name": "Bentley Systems", "role": "Direct", "horizon": "5y", "desc": "Digital twins for infrastructure."}
    },
    "Smart Energy": {
        "ENPH": {"name": "Enphase Energy", "role": "Direct", "horizon": "3y", "desc": "Microinverters creating decentralized grids."},
        "PLUG": {"name": "Plug Power", "role": "Direct", "horizon": "10y", "desc": "Green hydrogen ecosystem play."},
        "FLNC": {"name": "Fluence Energy", "role": "Direct", "horizon": "5y", "desc": "Grid-scale energy storage (Siemens/AES spinoff)."},
        "TSLA": {"name": "Tesla", "role": "Indirect", "horizon": "3y", "desc": "Virtual power plants and battery tech."},
        "QS": {"name": "QuantumScape", "role": "Direct", "horizon": "10y", "desc": "Solid-state batteries (Pre-revenue/High Risk)."}
    },
    "Smart Cities": {
        "PLTR": {"name": "Palantir", "role": "Direct", "horizon": "3y", "desc": "The OS for modern governance and defense."},
        "U": {"name": "Unity Software", "role": "Direct", "horizon": "5y", "desc": "Real-time 3D engine for digital twins."},
        "CSCO": {"name": "Cisco", "role": "Indirect", "horizon": "3y", "desc": "IoT networking backbone."},
        "JOBY": {"name": "Joby Aviation", "role": "Direct", "horizon": "5y", "desc": "eVTOL (Flying Taxis) for urban mobility."}
    },
    "Bio-Hacking": {
        "CRSP": {"name": "CRISPR Therapeutics", "role": "Direct", "horizon": "5y", "desc": "Gene editing technology."},
        "DNA": {"name": "Ginkgo Bioworks", "role": "Direct", "horizon": "10y", "desc": "Cell programming platform (Bio-foundry)."}
    }
}

class MoonshotScanner:
    def get_moonshots(self):
        """
        Fetches live data for the curated list.
        Returns a flat list of objects with Theme and Horizon for UI filtering.
        """
        results = []
        
        # Collect all tickers to fetch in batch (if yfinance supports, else loop)
        # For simplicity/reliability in this MVP, we loop but cache if we were pro.
        
        for theme, stocks in MOONSHOT_THEMES.items():
            for symbol, meta in stocks.items():
                try:
                    ticker = yf.Ticker(symbol)
                    info = ticker.info
                    
                    price = info.get('currentPrice', 0)
                    day_change = info.get('regularMarketChangePercent', 0)
                    mkt_cap = info.get('marketCap', 0)
                    
                    # Custom "Innovation Score" (Mock logic for MVP based on real metrics)
                    # Real logic would check R&D/Rev ratio.
                    # Here we proxy with Beta and Revenue Growth
                    rev_growth = info.get('revenueGrowth', 0)
                    beta = info.get('beta', 1.0)
                    
                    # Innovation Score: Higher Beta + High Growth = High Innovation Score
                    innovation_score = int(min((rev_growth * 100) + (beta * 10), 99))
                    if innovation_score < 10: innovation_score = random.randint(40, 80) # Fallback
                    
                    results.append({
                        "symbol": symbol,
                        "name": meta['name'],
                        "theme": theme,
                        "role": meta['role'], # Direct vs Indirect
                        "horizon": meta['horizon'], # 3y, 5y, 10y
                        "description": meta['desc'],
                        "price": round(price, 2),
                        "change_pct": round(day_change * 100, 2) if day_change else 0,
                        "market_cap": mkt_cap,
                        "innovation_score": innovation_score
                    })
                    
                except Exception as e:
                    print(f"Error fetching {symbol}: {e}")
                    # Include with fallback data so UI doesn't break
                    results.append({
                        "symbol": symbol,
                        "name": meta['name'],
                        "theme": theme,
                        "role": meta['role'],
                        "horizon": meta['horizon'],
                        "description": meta['desc'],
                        "price": 0,
                        "change_pct": 0,
                        "market_cap": 0,
                        "innovation_score": 50,
                        "error": True
                    })
                    
        return results
