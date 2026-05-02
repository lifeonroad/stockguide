"""
International Markets Scanner (Emerging India & Developed Canada)
=================================================================
Fetches and scores top picks from India (NSE) and Canada (TSX) based on growth, profitability, and valuation.
"""

import logging
from typing import List, Dict, Any, Optional
from cache_utils import timed_cache, sanitize_metric
from data_client import get_price_live, get_fundamentals

logger = logging.getLogger(__name__)

# Curated List of Emerging and International Picks
INTERNATIONAL_PICKS = {
    "India (Emerging Market)": {
        "RELIANCE.NS": {"name": "Reliance Industries", "desc": "Conglomerate dominating telecom, retail, and energy.", "type": "Core"},
        "TCS.NS": {"name": "Tata Consultancy Services", "desc": "IT services giant with high return on equity.", "type": "Quality Compounder"},
        "HDFCBANK.NS": {"name": "HDFC Bank", "desc": "India's largest private sector bank.", "type": "Financial Core"},
        "INFY.NS": {"name": "Infosys", "desc": "Global leader in next-generation digital services.", "type": "Quality Compounder"},
        "ADANIENT.NS": {"name": "Adani Enterprises", "desc": "Infrastructure and energy conglomerate.", "type": "High Growth / High Risk"},
        "BAJFINANCE.NS": {"name": "Bajaj Finance", "desc": "Leading non-banking financial company.", "type": "Growth Compounder"}
    },
    "Canada (Developed Market)": {
        "SHOP.TO": {"name": "Shopify", "desc": "E-commerce platform powering global retail.", "type": "Growth Leader"},
        "RY.TO": {"name": "Royal Bank of Canada", "desc": "Canada's largest bank by market cap.", "type": "Dividend Dividend Core"},
        "CP.TO": {"name": "Canadian Pacific Kansas City", "desc": "Transnational railway network.", "type": "Infrastructure Core"},
        "CSU.TO": {"name": "Constellation Software", "desc": "Serial acquirer of vertical market software.", "type": "Quality Compounder"},
        "BN.TO": {"name": "Brookfield Corp", "desc": "Global alternative asset manager.", "type": "Real Assets Core"},
        "CNQ.TO": {"name": "Canadian Natural Res.", "desc": "Major oil and gas producer.", "type": "Commodity Play"}
    }
}

class InternationalScanner:
    @timed_cache(ttl_seconds=3600)  # Cache for 1 hour
    def get_picks(self) -> Dict[str, List[Dict[str, Any]]]:
        """Scans and scores curated international stocks."""
        import concurrent.futures

        results = {
            "India (Emerging Market)": [],
            "Canada (Developed Market)": []
        }
        
        tasks_meta = []
        for region, stocks in INTERNATIONAL_PICKS.items():
            for symbol, meta in stocks.items():
                tasks_meta.append((symbol, region, meta))
                
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(self._score_stock, sym, reg, m): reg for sym, reg, m in tasks_meta}
            for future in concurrent.futures.as_completed(futures):
                pick = future.result()
                if pick:
                    results[pick['region']].append(pick)
                    
        for region in results:
            results[region] = sorted(results[region], key=lambda x: x.get('moat_score', 0), reverse=True)
            
        return results

    def _score_stock(self, symbol: str, region: str, meta: Dict) -> Optional[Dict]:
        try:
            live = get_price_live(symbol)
            fund = get_fundamentals(symbol)
            
            if not fund or not live:
                return self._fallback_data(symbol, region, meta)
                
            price = live.get('price', 0)
            if price == 0:
                 return self._fallback_data(symbol, region, meta)
                 
            day_change = live.get('change_pct', 0)
            mkt_cap = fund.get('marketCap') or live.get('mkt_cap', 0)
            
            pe = sanitize_metric(fund.get('trailingPE'), 999)
            roe = sanitize_metric(fund.get('returnOnEquity'), 0) * 100
            rev_growth = sanitize_metric(fund.get('revenueGrowth'), 0) * 100
            
            # Calculate Profit Margin
            rev = fund.get('revenue', 0)
            ni = fund.get('netIncome', 0)
            margin = (ni / rev * 100) if rev else 0.0
            margin = sanitize_metric(margin, 0)
            
            # Calculate Moat Score (0-100)
            # Higher ROE, Higher Margin, Higher Growth = Better Score
            # Penalty for high P/E
            score = (roe * 1.5) + (margin * 1.0) + (rev_growth * 0.5)
            if pe > 0 and pe < 100:
                score -= (pe * 0.2)
                
            moat_score = int(min(max(score, 10), 98))
            
            # Map ticker format for TradingView (NSE:RELIANCE, TSX:SHOP)
            tv_symbol = symbol
            if symbol.endswith(".NS"):
                tv_symbol = f"NSE:{symbol.replace('.NS', '')}"
            elif symbol.endswith(".TO"):
                tv_symbol = f"TSX:{symbol.replace('.TO', '')}"
                
            return {
                "symbol": symbol,
                "tv_symbol": tv_symbol,
                "name": meta['name'],
                "region": region,
                "type": meta['type'],
                "description": meta['desc'],
                "price": round(price, 2),
                "change_pct": round(day_change * 100, 2) if day_change else 0,
                "market_cap": mkt_cap,
                "pe": round(pe, 1) if pe != 999 else "N/A",
                "roe": round(roe, 1),
                "margin": round(margin, 1),
                "rev_growth": round(rev_growth, 1),
                "moat_score": moat_score
            }
            
        except Exception as e:
            logger.warning(f"Error fetching international stock {symbol}: {e}")
            return self._fallback_data(symbol, region, meta)
        try:
            live = get_price_live(symbol)
            fund = get_fundamentals(symbol)
            
            if not fund or not live:
                return self._fallback_data(symbol, region, meta)
                
            price = live.get('price', 0)
            if price == 0:
                 return self._fallback_data(symbol, region, meta)
                 
            day_change = live.get('change_pct', 0)
            mkt_cap = fund.get('marketCap') or live.get('mkt_cap', 0)
            
            pe = sanitize_metric(fund.get('trailingPE'), 999)
            roe = sanitize_metric(fund.get('returnOnEquity'), 0) * 100
            rev_growth = sanitize_metric(fund.get('revenueGrowth'), 0) * 100
            
            # Calculate Profit Margin
            rev = fund.get('revenue', 0)
            ni = fund.get('netIncome', 0)
            margin = (ni / rev * 100) if rev else 0.0
            margin = sanitize_metric(margin, 0)
            
            # Calculate Moat Score (0-100)
            # Higher ROE, Higher Margin, Higher Growth = Better Score
            # Penalty for high P/E
            score = (roe * 1.5) + (margin * 1.0) + (rev_growth * 0.5)
            if pe > 0 and pe < 100:
                score -= (pe * 0.2)
                
            moat_score = int(min(max(score, 10), 98))
            
            # Map ticker format for TradingView (NSE:RELIANCE, TSX:SHOP)
            tv_symbol = symbol
            if symbol.endswith(".NS"):
                tv_symbol = f"NSE:{symbol.replace('.NS', '')}"
            elif symbol.endswith(".TO"):
                tv_symbol = f"TSX:{symbol.replace('.TO', '')}"
                
            return {
                "symbol": symbol,
                "tv_symbol": tv_symbol,
                "name": meta['name'],
                "region": region,
                "type": meta['type'],
                "description": meta['desc'],
                "price": round(price, 2),
                "change_pct": round(day_change * 100, 2) if day_change else 0,
                "market_cap": mkt_cap,
                "pe": round(pe, 1) if pe != 999 else "N/A",
                "roe": round(roe, 1),
                "margin": round(margin, 1),
                "rev_growth": round(rev_growth, 1),
                "moat_score": moat_score
            }
            
        except Exception as e:
            logger.warning(f"Error fetching international stock {symbol}: {e}")
            return self._fallback_data(symbol, region, meta)

    def _fallback_data(self, symbol: str, region: str, meta: Dict) -> Dict:
        tv_symbol = symbol
        if symbol.endswith(".NS"):
            tv_symbol = f"NSE:{symbol.replace('.NS', '')}"
        elif symbol.endswith(".TO"):
            tv_symbol = f"TSX:{symbol.replace('.TO', '')}"
            
        return {
            "symbol": symbol,
            "tv_symbol": tv_symbol,
            "name": meta['name'],
            "region": region,
            "type": meta['type'],
            "description": meta['desc'],
            "price": 0,
            "change_pct": 0,
            "market_cap": 0,
            "pe": "N/A",
            "roe": 0,
            "margin": 0,
            "rev_growth": 0,
            "moat_score": 50,
            "error": True
        }
