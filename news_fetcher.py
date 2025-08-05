import requests
from datetime import datetime, timedelta
import json
import time
from typing import List, Dict, Optional
import logging
from urllib.parse import quote

class NewsFetcher:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.news_cache = {}
        self.cache_duration = timedelta(minutes=30)
        self.logger = logging.getLogger(__name__)
        
    def fetch_stock_news(self, symbol: str) -> List[Dict]:
        """Fetch latest news for a stock symbol using multiple sources"""
        cache_key = f"{symbol}_news"
        
        # Check cache
        if cache_key in self.news_cache:
            cached_time, cached_data = self.news_cache[cache_key]
            if datetime.now() - cached_time < self.cache_duration:
                return cached_data
        
        all_news = []
        
        # Try NewsAPI if API key is available
        if self.api_key:
            try:
                newsapi_articles = self._fetch_newsapi(symbol)
                all_news.extend(newsapi_articles)
            except Exception as e:
                self.logger.error(f"NewsAPI error for {symbol}: {e}")
        
        # Try Yahoo Finance news
        try:
            yahoo_news = self._fetch_yahoo_news(symbol)
            all_news.extend(yahoo_news)
        except Exception as e:
            self.logger.error(f"Yahoo news error for {symbol}: {e}")
        
        # Try Google News RSS
        try:
            google_news = self._fetch_google_news(symbol)
            all_news.extend(google_news)
        except Exception as e:
            self.logger.error(f"Google news error for {symbol}: {e}")
        
        # Sort by timestamp (most recent first)
        all_news.sort(key=lambda x: x.get('published_at', ''), reverse=True)
        
        # Cache results
        self.news_cache[cache_key] = (datetime.now(), all_news[:10])
        
        return all_news[:10]
    
    def _fetch_newsapi(self, symbol: str) -> List[Dict]:
        """Fetch news from NewsAPI"""
        url = f"https://newsapi.org/v2/everything"
        params = {
            'q': f'"{symbol}" stock',
            'apiKey': self.api_key,
            'language': 'en',
            'sortBy': 'publishedAt',
            'pageSize': 5,
            'from': (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        }
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            articles = []
            for article in data.get('articles', []):
                articles.append({
                    'title': article.get('title', ''),
                    'description': article.get('description', ''),
                    'url': article.get('url', ''),
                    'source': article.get('source', {}).get('name', 'NewsAPI'),
                    'published_at': article.get('publishedAt', ''),
                    'sentiment': self._analyze_sentiment(article.get('title', '') + ' ' + article.get('description', ''))
                })
            return articles
        return []
    
    def _fetch_yahoo_news(self, symbol: str) -> List[Dict]:
        """Fetch news from Yahoo Finance"""
        import yfinance as yf
        
        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news
            
            articles = []
            for item in news[:5]:
                articles.append({
                    'title': item.get('title', ''),
                    'description': item.get('title', ''),  # Yahoo doesn't always provide description
                    'url': item.get('link', ''),
                    'source': 'Yahoo Finance',
                    'published_at': datetime.fromtimestamp(item.get('providerPublishTime', 0)).isoformat(),
                    'sentiment': self._analyze_sentiment(item.get('title', ''))
                })
            return articles
        except Exception as e:
            self.logger.error(f"Yahoo Finance news error: {e}")
            return []
    
    def _fetch_google_news(self, symbol: str) -> List[Dict]:
        """Fetch news from Google News RSS"""
        try:
            import feedparser
        except ImportError:
            return []
            
        rss_url = f"https://news.google.com/rss/search?q={quote(symbol + ' stock')}&hl=en-US&gl=US&ceid=US:en"
        
        feed = feedparser.parse(rss_url)
        articles = []
        
        for entry in feed.entries[:5]:
            articles.append({
                'title': entry.get('title', ''),
                'description': entry.get('summary', ''),
                'url': entry.get('link', ''),
                'source': 'Google News',
                'published_at': entry.get('published', ''),
                'sentiment': self._analyze_sentiment(entry.get('title', '') + ' ' + entry.get('summary', ''))
            })
        
        return articles
    
    def _analyze_sentiment(self, text: str) -> str:
        """Simple sentiment analysis based on keywords"""
        positive_words = ['gain', 'rise', 'up', 'high', 'surge', 'rally', 'buy', 'upgrade', 'beat', 'exceed', 'strong', 'growth', 'profit']
        negative_words = ['loss', 'fall', 'down', 'low', 'drop', 'sell', 'downgrade', 'miss', 'weak', 'decline', 'warning', 'cut']
        
        text_lower = text.lower()
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count > negative_count:
            return 'positive'
        elif negative_count > positive_count:
            return 'negative'
        else:
            return 'neutral'