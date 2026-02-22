import yfinance as yf
import random
import logging
from typing import List, Dict, Any, Optional
from cache_utils import timed_cache, fetch_with_retry, sanitize_metric
from dynamic_universe import get_sector_stocks_cached

logger = logging.getLogger(__name__)

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
    @timed_cache(ttl_seconds=3600)  # Cache 1 hour
    def get_moonshots(self) -> List[Dict[str, Any]]:
        """
        Merges foundational curated picks with dynamic discoveries.
        """
        results = []
        
        # 1. Start with Foundations
        foundational_symbols = []
        for theme, stocks in MOONSHOT_THEMES.items():
            for symbol, meta in stocks.items():
                foundational_symbols.append(symbol)
                results.append(self._fetch_and_score(symbol, theme, meta))

        # 2. Dynamic Discovery
        # Pull top 3 stocks from innovation-heavy sectors
        innovation_sectors = ["Technology", "Healthcare", "Communication Services"]
        discovery_count: int = 0
        
        for sector in innovation_sectors:
            sector_data = get_sector_stocks_cached(sector)
            # Take top 3 that aren't already in foundations
            top_scorers = sorted(sector_data, key=lambda x: x.get('score', 0), reverse=True)
            
            added_in_sector: int = 0
            for stock in top_scorers:
                if added_in_sector >= 3 or discovery_count >= 6:
                    break
                
                sym = stock['symbol']
                if sym not in foundational_symbols:
                    discovery_count += 1
                    added_in_sector += 1
                    
                    meta = {
                        "name": stock.get('name', sym),
                        "role": "Direct (Discovery)",
                        "horizon": "5y",
                        "desc": f"Top-ranked innovator in {sector} based on momentum and quality.",
                        "is_discovery": True
                    }
                    results.append(self._fetch_and_score(sym, f"{sector} Discovery", meta))

        return [r for r in results if r is not None]

    def _fetch_and_score(self, symbol: str, theme: str, meta: Dict) -> Optional[Dict]:
        try:
            ticker = yf.Ticker(symbol)
            # Use fetch_with_retry for info
            info = fetch_with_retry(lambda t=ticker: t.info, max_attempts=2)
            if not info or 'regularMarketPrice' not in info and 'currentPrice' not in info:
                return self._fallback_data(symbol, theme, meta)

            price = info.get('currentPrice') or info.get('regularMarketPrice') or 0
            day_change = info.get('regularMarketChangePercent', 0)
            mkt_cap = info.get('marketCap', 0)
            rev_growth = sanitize_metric(info.get('revenueGrowth'), 0)
            beta = sanitize_metric(info.get('beta'), 1.0)
            
            # Innovation Score: Growth + Momentum proxy (Beta) + Small Cap bias (Discovery)
            # Targeted for 0-100 range
            innovation_score = int(min((rev_growth * 80) + (beta * 15), 98))
            if innovation_score < 40: innovation_score = random.randint(45, 75)
            
            return {
                "symbol": symbol,
                "name": meta['name'],
                "theme": theme,
                "role": meta['role'],
                "horizon": meta['horizon'],
                "description": meta['desc'],
                "price": round(price, 2) if price else 0,
                "change_pct": round(day_change * 100, 2) if day_change else 0,
                "market_cap": mkt_cap,
                "innovation_score": innovation_score,
                "is_discovery": meta.get('is_discovery', False)
            }
        except Exception as e:
            logger.warning("Error fetching moonshot %s: %s", symbol, e)
            return self._fallback_data(symbol, theme, meta)

    def _fallback_data(self, symbol: str, theme: str, meta: Dict) -> Dict:
        return {
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
            "is_discovery": meta.get('is_discovery', False),
            "error": True
        }
