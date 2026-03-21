"""
News aggregation service for the Musk Ecosystem Intelligence app.
Aggregates news from Finnhub, RSS feeds, and performs sentiment analysis.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from app.services.finnhub_client import FinnhubService

logger = logging.getLogger(__name__)


class NewsService:
    """
    News aggregation service.

    Combines news from Finnhub API, RSS feeds (Reuters, Bloomberg, TechCrunch),
    and Google News. Includes sentiment analysis.
    """

    # Companies tracked in the Musk ecosystem
    ECOSYSTEM_COMPANIES = {
        "Tesla": {"ticker": "TSLA", "keywords": ["Tesla", "TSLA", "Elon Musk"]},
        "SpaceX": {"keywords": ["SpaceX", "Starship", "rocket", "launch"]},
        "The Boring Company": {"keywords": ["Boring Company", "tunnel"]},
        "Neuralink": {"keywords": ["Neuralink", "neural", "implant"]},
        "X (Twitter)": {"keywords": ["X Corp", "Twitter", "Elon Musk social"]},
        "Dogecoin": {"keywords": ["Dogecoin", "DOGE", "cryptocurrency"]},
    }

    # Sentiment analysis word lists
    POSITIVE_WORDS = {
        "gain", "growth", "profit", "surge", "jump", "rally", "bull",
        "strong", "outperform", "beat", "success", "breakthrough", "innovation",
        "advance", "rise", "positive", "excellent", "bullish", "record",
        "boom", "momentum", "accelerate", "expand", "upgrade",
    }

    NEGATIVE_WORDS = {
        "loss", "decline", "drop", "crash", "bear", "weak", "miss",
        "fail", "failure", "risk", "decline", "fall", "negative",
        "concern", "warning", "bearish", "downgrade", "slump",
        "crisis", "collapse", "worse", "deteriorate", "plunge",
    }

    RSS_FEEDS = {
        "reuters_tech": "https://feeds.reuters.com/reuters/technologyNews",
        "bloomberg_tech": "https://www.bloomberg.com/feed/podcast/etf-report.xml",
        "techcrunch": "https://techcrunch.com/feed/",
    }

    def __init__(self, finnhub_key: Optional[str] = None, timeout: int = 10):
        """
        Initialize news service.

        Args:
            finnhub_key: Optional Finnhub API key
            timeout: Request timeout in seconds
        """
        self.finnhub = FinnhubService(api_key=finnhub_key, timeout=timeout)
        self.timeout = timeout

    def _fetch_rss_feed(self, url: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Fetch and parse RSS feed.

        Args:
            url: RSS feed URL
            limit: Maximum articles to extract

        Returns:
            List of article dicts, empty list on failure
        """
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "xml")
            items = soup.find_all("item")[:limit]

            articles = []
            for item in items:
                try:
                    article = {
                        "title": item.find("title"),
                        "summary": item.find("description"),
                        "url": item.find("link"),
                        "published_at": item.find("pubDate"),
                        "source": "RSS Feed",
                    }

                    # Extract text content safely
                    article = {
                        k: str(v.text).strip() if v else None
                        for k, v in article.items()
                    }

                    if article.get("title"):
                        articles.append(article)
                except Exception as e:
                    logger.warning(f"Error parsing RSS item: {e}")
                    continue

            return articles
        except Exception as e:
            logger.error(f"Error fetching RSS feed {url}: {e}")
            return []

    def _fetch_google_news(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fallback: Fetch news from Google News (simple scraping).

        Note: This is a basic implementation. Google News blocking may apply.

        Args:
            query: Search query
            limit: Maximum articles

        Returns:
            List of article dicts, empty list on failure
        """
        try:
            url = "https://news.google.com/rss"
            params = {"q": query}

            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "xml")
            items = soup.find_all("item")[:limit]

            articles = []
            for item in items:
                try:
                    article = {
                        "title": str(item.find("title").text).strip() if item.find("title") else None,
                        "summary": str(item.find("description").text).strip() if item.find("description") else None,
                        "url": str(item.find("link").text).strip() if item.find("link") else None,
                        "published_at": str(item.find("pubDate").text).strip() if item.find("pubDate") else None,
                        "source": "Google News",
                    }

                    if article.get("title"):
                        articles.append(article)
                except Exception as e:
                    logger.warning(f"Error parsing Google News item: {e}")
                    continue

            return articles
        except Exception as e:
            logger.warning(f"Error fetching Google News: {e}")
            return []

    def analyze_sentiment(self, text: str) -> float:
        """
        Analyze sentiment of text using keyword-based approach.

        Args:
            text: Text to analyze

        Returns:
            Sentiment score from -1 (very negative) to 1 (very positive)
        """
        if not text:
            return 0.0

        text_lower = text.lower()

        # Count positive and negative words
        positive_count = sum(1 for word in self.POSITIVE_WORDS if word in text_lower)
        negative_count = sum(1 for word in self.NEGATIVE_WORDS if word in text_lower)

        total = positive_count + negative_count
        if total == 0:
            return 0.0

        # Calculate sentiment score
        sentiment = (positive_count - negative_count) / total
        return max(-1.0, min(1.0, sentiment))  # Clamp to [-1, 1]

    def _extract_mentioned_companies(self, text: str) -> List[str]:
        """
        Extract mentioned companies from text.

        Args:
            text: Text to analyze

        Returns:
            List of company names mentioned
        """
        mentioned = []
        text_lower = text.lower()

        for company, data in self.ECOSYSTEM_COMPANIES.items():
            for keyword in data.get("keywords", []):
                if keyword.lower() in text_lower:
                    mentioned.append(company)
                    break

        return list(set(mentioned))  # Remove duplicates

    def get_ecosystem_news(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get aggregated news for all tracked companies.

        Args:
            limit: Maximum articles to return

        Returns:
            List of news article dicts
        """
        all_articles = []

        # Fetch from Finnhub for Tesla
        finnhub_articles = self.finnhub.get_company_news(
            "TSLA",
            (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
            datetime.now().strftime("%Y-%m-%d"),
            limit=limit,
        )

        if finnhub_articles:
            for article in finnhub_articles:
                article["mentioned_companies"] = self._extract_mentioned_companies(
                    f"{article.get('title', '')} {article.get('summary', '')}"
                )
                article["sentiment"] = self.analyze_sentiment(
                    f"{article.get('title', '')} {article.get('summary', '')}"
                )
                all_articles.append(article)

        # Fetch from RSS feeds
        for feed_name, feed_url in self.RSS_FEEDS.items():
            rss_articles = self._fetch_rss_feed(feed_url, limit=limit // len(self.RSS_FEEDS))
            for article in rss_articles:
                article["mentioned_companies"] = self._extract_mentioned_companies(
                    f"{article.get('title', '')} {article.get('summary', '')}"
                )
                article["sentiment"] = self.analyze_sentiment(
                    f"{article.get('title', '')} {article.get('summary', '')}"
                )
                all_articles.append(article)

        # Sort by published date (most recent first)
        all_articles.sort(
            key=lambda x: x.get("published_at", ""),
            reverse=True,
        )

        return all_articles[:limit]

    def get_company_news(self, company_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get news for a specific company.

        Args:
            company_id: Company identifier (ticker or name)
            limit: Maximum articles to return

        Returns:
            List of news article dicts
        """
        # Map company names to tickers
        ticker_map = {
            "Tesla": "TSLA",
            "Tesla Inc": "TSLA",
            "TSLA": "TSLA",
        }

        ticker = ticker_map.get(company_id, company_id)

        articles = []

        # Try Finnhub first
        try:
            finnhub_articles = self.finnhub.get_company_news(
                ticker,
                (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                datetime.now().strftime("%Y-%m-%d"),
                limit=limit,
            )

            for article in finnhub_articles:
                article["mentioned_companies"] = self._extract_mentioned_companies(
                    f"{article.get('title', '')} {article.get('summary', '')}"
                )
                article["sentiment"] = self.analyze_sentiment(
                    f"{article.get('title', '')} {article.get('summary', '')}"
                )
                articles.append(article)
        except Exception as e:
            logger.error(f"Error fetching company news for {company_id}: {e}")

        # Fallback to Google News
        if not articles:
            google_articles = self._fetch_google_news(company_id, limit=limit)
            for article in google_articles:
                article["mentioned_companies"] = self._extract_mentioned_companies(
                    f"{article.get('title', '')} {article.get('summary', '')}"
                )
                article["sentiment"] = self.analyze_sentiment(
                    f"{article.get('title', '')} {article.get('summary', '')}"
                )
                articles.append(article)

        return articles[:limit]

    def get_trending_news(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get trending news with highest relevance and recency.

        Args:
            limit: Maximum articles to return

        Returns:
            List of trending news article dicts
        """
        articles = self.get_ecosystem_news(limit=limit * 3)

        # Score articles by recency and sentiment intensity
        for article in articles:
            try:
                # Parse publication date
                pub_date = datetime.fromisoformat(
                    article.get("published_at", "").replace("Z", "+00:00")
                )
                age_hours = (datetime.now(pub_date.tzinfo) - pub_date).total_seconds() / 3600
                recency_score = max(0, 1 - (age_hours / 72))  # Decay over 3 days
            except Exception:
                recency_score = 0.5

            # Sentiment intensity score
            sentiment_intensity = abs(article.get("sentiment", 0))

            # Company relevance score (if multiple companies mentioned)
            relevance_score = len(article.get("mentioned_companies", [])) / len(self.ECOSYSTEM_COMPANIES)

            # Combined trend score
            article["trend_score"] = (
                (recency_score * 0.5) +
                (sentiment_intensity * 0.3) +
                (relevance_score * 0.2)
            )

        # Sort by trend score
        articles.sort(key=lambda x: x.get("trend_score", 0), reverse=True)

        return articles[:limit]

    def search_news(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search for news matching a query.

        Args:
            query: Search query string
            limit: Maximum articles to return

        Returns:
            List of matching article dicts
        """
        all_articles = self.get_ecosystem_news(limit=limit * 2)

        # Simple text search
        query_lower = query.lower()
        matching_articles = [
            article for article in all_articles
            if (
                query_lower in article.get("title", "").lower() or
                query_lower in article.get("summary", "").lower()
            )
        ]

        return matching_articles[:limit]

    def get_sentiment_summary(self) -> Dict[str, Any]:
        """
        Get overall sentiment summary for ecosystem.

        Returns:
            Dict with sentiment statistics
        """
        articles = self.get_ecosystem_news(limit=100)

        if not articles:
            return {
                "average_sentiment": 0.0,
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
                "total_articles": 0,
            }

        sentiments = [article.get("sentiment", 0) for article in articles]

        positive = sum(1 for s in sentiments if s > 0.1)
        negative = sum(1 for s in sentiments if s < -0.1)
        neutral = len(sentiments) - positive - negative

        return {
            "average_sentiment": sum(sentiments) / len(sentiments),
            "positive_count": positive,
            "negative_count": negative,
            "neutral_count": neutral,
            "total_articles": len(articles),
            "sentiment_distribution": {
                "positive_percent": round(100 * positive / len(sentiments), 1),
                "negative_percent": round(100 * negative / len(sentiments), 1),
                "neutral_percent": round(100 * neutral / len(sentiments), 1),
            },
        }
