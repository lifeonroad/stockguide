"""
Contrarian Investing Opportunities Module

Identifies and scores contrarian investment opportunities by aggregating multiple signals:
- Fallen Angels (quality stocks beaten down)
- Burry's Orphans (neglected by Wall Street)
- Insider Buying (cluster buying activity)

Scoring Formula:
- Price Dislocation: 30% (52w return)
- Insider Confidence: 25% (buying activity)
- Value Metrics: 20% (PE, P/B, yield)
- Sentiment Extreme: 15% (downgrades, short interest)
- Catalyst Potential: 10% (new CEO, activist)
"""

from screeners import ScreenerEngine

def calculate_contrarian_score(stock_metrics, signal_type):
    """
    Calculate a 0-100 contrarian score for a stock.
    
    Scoring breakdown:
    - Price Dislocation (30 pts): How beaten down is it?
    - Value Metrics (20 pts): PE, P/B, Yield
    - Fundamentals Quality (20 pts): ROE, margins
    - Neglect Factor (20 pts): Institutional ownership
    - Growth Stability (10 pts): Not dying
    """
    score = 0
    
    # Price Dislocation (0-30 pts)
    w52_return = stock_metrics.get('52w_return', 0)
    if w52_return < -50:
        score += 30
    elif w52_return < -40:
        score += 25
    elif w52_return < -30:
        score += 20
    elif w52_return < -20:
        score += 10
    
    # Value Metrics (0-20 pts)
    pe = stock_metrics.get('pe', 999)
    pb = stock_metrics.get('pb', 999)
    div_yield = stock_metrics.get('div_yield', 0)
    
    if 0 < pe < 8:
        score += 10
    elif 0 < pe < 12:
        score += 7
    elif 0 < pe < 15:
        score += 5
    
    if pb < 1.0:
        score += 5
    elif pb < 1.5:
        score += 3
    
    if div_yield > 5:
        score += 5
    elif div_yield > 3:
        score += 3
    
    # Fundamentals Quality (0-20 pts)
    roe = stock_metrics.get('roe', 0)
    margin = stock_metrics.get('margin', 0)
    
    if roe > 15:
        score += 10
    elif roe > 10:
        score += 7
    elif roe > 5:
        score += 4
    
    if margin > 15:
        score += 10
    elif margin > 10:
        score += 7
    elif margin > 5:
        score += 4
    
    # Neglect Factor (0-20 pts) - Only for orphans
    if signal_type == 'burry_orphans':
        inst_ownership = stock_metrics.get('inst_ownership', 100)
        if inst_ownership < 20:
            score += 20
        elif inst_ownership < 30:
            score += 15
        elif inst_ownership < 40:
            score += 10
    else:
        # For fallen angels, give points for being beaten down
        if w52_return < -40:
            score += 15
        elif w52_return < -35:
            score += 10
    
    # Growth Stability (0-10 pts)
    rev_growth = stock_metrics.get('rev_growth', -100)
    if rev_growth > 5:
        score += 10
    elif rev_growth > 0:
        score += 7
    elif rev_growth > -10:
        score += 5
    
    return min(score, 100)  # Cap at 100

def get_contrarian_opportunities():
    """
    Aggregates contrarian opportunities from multiple screeners.
    Returns ranked list with scores.
    """
    engine = ScreenerEngine()
    
    # Run the contrarian screeners
    fallen_angels = engine.run_screen('fallen_angels')
    burry_orphans = engine.run_screen('burry_orphans')
    
    opportunities = []
    
    # Process Fallen Angels
    for stock in fallen_angels:
        score = calculate_contrarian_score(stock['metrics'], 'fallen_angels')
        opportunities.append({
            'symbol': stock['symbol'],
            'name': stock['name'],
            'score': score,
            'price_change_52w': stock['metrics']['52w_return'],
            'reason': stock['reason'],
            'signal': 'fallen_angels',
            'pe': stock['metrics']['pe'],
            'roe': stock['metrics']['roe'],
            'debt_equity': stock['metrics']['debt_equity']
        })
    
    # Process Burry's Orphans
    for stock in burry_orphans:
        score = calculate_contrarian_score(stock['metrics'], 'burry_orphans')
        opportunities.append({
            'symbol': stock['symbol'],
            'name': stock['name'],
            'score': score,
            'price_change_52w': stock['metrics']['52w_return'],
            'reason': stock['reason'],
            'signal': 'burry_orphans',
            'pe': stock['metrics']['pe'],
            'inst_ownership': stock['metrics']['inst_ownership'],
            'market_cap': stock['metrics']['market_cap']
        })
    
    # Sort by score (highest first)
    opportunities.sort(key=lambda x: x['score'], reverse=True)
    
    return {
        'opportunities': opportunities,
        'total_count': len(opportunities),
        'high_conviction': len([o for o in opportunities if o['score'] >= 70]),
        'avg_score': sum(o['score'] for o in opportunities) / len(opportunities) if opportunities else 0
    }
