"""
Market News Module
Fetches and parses RSS feeds from major financial news sources.
"""

import feedparser
from datetime import datetime
from cache_utils import timed_cache


@timed_cache(ttl_seconds=3600, soft_ttl_seconds=2700)  # 1h hard, 45m soft (SWR)
def get_market_news():
    """
    Fetches market news from RSS feeds.
    
    Returns list of news items with:
    - title
    - link
    - published (time ago)
    - source
    """
    
    news_items = []
    
    # RSS Feed sources
    feeds = {
        'Yahoo Finance': 'https://finance.yahoo.com/news/rssindex',
        'Reuters Business': 'https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best',
        'MarketWatch': 'https://www.marketwatch.com/rss/topstories'
    }
    
    for source_name, feed_url in feeds.items():
        try:
            feed = feedparser.parse(feed_url)
            
            for entry in feed.entries[:10]:  # Top 10 from each source
                news_items.append({
                    'title': entry.get('title', 'No title'),
                    'link': entry.get('link', '#'),
                    'published': format_time_ago(entry.get('published_parsed')),
                    'source': source_name,
                    'summary': entry.get('summary', '')[:200] if entry.get('summary') else ''
                })
        except Exception as e:
            print(f"Error fetching {source_name}: {e}")
    
    # Sort by recency (newest first)
    # Since we're combining multiple feeds, we'll just return them in order
    return {
        'news': news_items[:30],  # Return top 30 total
        'last_updated': datetime.now().isoformat(),
        'sources': list(feeds.keys())
    }


def format_time_ago(published_parsed):
    """Convert time tuple to 'X hours ago' format."""
    if not published_parsed:
        return 'Unknown'
    
    try:
        from datetime import timezone
        import time
        
        # Convert time struct to datetime
        published_dt = datetime(*published_parsed[:6])
        now = datetime.now()
        
        diff = now - published_dt
        
        hours = int(diff.total_seconds() / 3600)
        minutes = int(diff.total_seconds() / 60)
        
        if hours < 1:
            return f"{minutes}m ago"
        elif hours < 24:
            return f"{hours}h ago"
        else:
            days = int(hours / 24)
            return f"{days}d ago"
    except:
        return 'Unknown'
