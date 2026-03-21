"""
Finnhub API client service for market data and news.
Provides free-tier access to stock quotes, company profiles, and market news.
"""

import logging
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class FinnhubService:
    """
    Client for Finnhub API (free-tier).

    Retrieves stock quotes, company profiles, news, and market data.
    Implements rate limiting for 60 requests/minute constraint.
    """

    def __init__(self, api_key: Optional[str] = None, timeout: int = 10):
        """
        Initialize Finnhub service.

        Args:
            api_key: Optional Finnhub API key (not required for basic endpoints)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.base_url = "https://finnhub.io/api/v1"
        self.timeout = timeout
        self._request_times: List[float] = []
        self._rate_limit = 60  # requests per minute

    def _check_rate_limit(self) -> None:
        """
        Check and enforce rate limit (60 requests per minute).

        Sleeps if necessary to avoid exceeding the limit.
        """
        now = time.time()
        # Remove request times older than 1 minute
        self._request_times = [t for t in self._request_times if now - t < 60]

        if len(self._request_times) >= self._rate_limit:
            sleep_time = 60 - (now - self._request_times[0]) + 0.1
            if sleep_time > 0:
                logger.warning(f"Rate limit approaching. Sleeping {sleep_time:.1f}s")
                time.sleep(sleep_time)
            self._request_times = []

        self._request_times.append(now)

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Make a request to Finnhub API with rate limiting.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            Response JSON as dict, or None on failure
        """
        try:
            self._check_rate_limit()

            url = f"{self.base_url}/{endpoint}"
            request_params = params or {}

            if self.api_key:
                request_params["token"] = self.api_key

            response = requests.get(
                url,
                params=request_params,
                timeout=self.timeout,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Finnhub API error for {endpoint}: {e}")
            return None
        except ValueError as e:
            logger.error(f"Finnhub JSON decode error for {endpoint}: {e}")
            return None

    def get_quote(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get current stock quote.

        Args:
            ticker: Stock ticker symbol (e.g., 'TSLA')

        Returns:
            Dict with current price, open, high, low, change%, or None on failure
        """
        try:
            data = self._make_request("quote", {"symbol": ticker})
            if not data or data.get("c") is None:
                return None

            return {
                "ticker": ticker,
                "current_price": data.get("c"),
                "previous_close": data.get("pc"),
                "open": data.get("o"),
                "high": data.get("h"),
                "low": data.get("l"),
                "change": data.get("d"),
                "change_percent": data.get("dp"),
                "timestamp": data.get("t"),
            }
        except Exception as e:
            logger.error(f"Error getting quote for {ticker}: {e}")
            return None

    def get_company_profile(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get company profile information.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with name, sector, market cap, logo URL, or None on failure
        """
        try:
            data = self._make_request("stock/profile2", {"symbol": ticker})
            if not data or not data.get("name"):
                return None

            return {
                "ticker": ticker,
                "name": data.get("name"),
                "country": data.get("country"),
                "currency": data.get("currency"),
                "exchange": data.get("exchange"),
                "industry": data.get("finnhubIndustry"),
                "sector": data.get("finnhubIndustry"),
                "market_cap": data.get("marketCapitalization"),
                "ipo_date": data.get("ipo"),
                "logo_url": data.get("logo"),
                "website": data.get("weburl"),
                "phone": data.get("phone"),
            }
        except Exception as e:
            logger.error(f"Error getting company profile for {ticker}: {e}")
            return None

    def get_company_news(
        self,
        ticker: str,
        from_date: str,
        to_date: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get company news articles.

        Args:
            ticker: Stock ticker symbol
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            limit: Maximum number of articles

        Returns:
            List of news article dicts, empty list on failure
        """
        try:
            data = self._make_request(
                "company-news",
                {
                    "symbol": ticker,
                    "from": from_date,
                    "to": to_date,
                },
            )

            if not data:
                return []

            articles = data if isinstance(data, list) else data.get("news", [])

            return [
                {
                    "id": article.get("id"),
                    "title": article.get("headline"),
                    "summary": article.get("summary"),
                    "source": article.get("source"),
                    "url": article.get("url"),
                    "image": article.get("image"),
                    "category": article.get("category"),
                    "published_at": article.get("datetime"),
                }
                for article in articles[:limit]
            ]
        except Exception as e:
            logger.error(f"Error getting news for {ticker}: {e}")
            return []

    def get_market_status(self) -> Optional[Dict[str, Any]]:
        """
        Get current market status.

        Returns:
            Dict with market open status, or None on failure
        """
        try:
            data = self._make_request("market-status")
            if not data:
                return None

            return {
                "market_open": data.get("isOpen"),
                "us_market_open": data.get("isUSMarketOpen"),
                "timestamp": data.get("t"),
            }
        except Exception as e:
            logger.error(f"Error getting market status: {e}")
            return None

    def get_peers(self, ticker: str, limit: int = 10) -> List[str]:
        """
        Get list of peer companies.

        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of peers to return

        Returns:
            List of peer ticker symbols, empty list on failure
        """
        try:
            data = self._make_request("stock/peers", {"symbol": ticker})
            if not data or not isinstance(data, list):
                return []

            return data[:limit]
        except Exception as e:
            logger.error(f"Error getting peers for {ticker}: {e}")
            return []

    def get_stock_splits(self, ticker: str) -> List[Dict[str, Any]]:
        """
        Get stock split history.

        Args:
            ticker: Stock ticker symbol

        Returns:
            List of stock split dicts, empty list on failure
        """
        try:
            data = self._make_request("stock/split", {"symbol": ticker})
            if not data or not isinstance(data, list):
                return []

            return [
                {
                    "from_factor": split.get("fromFactor"),
                    "to_factor": split.get("toFactor"),
                    "date": split.get("date"),
                }
                for split in data
            ]
        except Exception as e:
            logger.error(f"Error getting stock splits for {ticker}: {e}")
            return []

    def get_earnings_surprises(self, ticker: str) -> List[Dict[str, Any]]:
        """
        Get historical earnings surprises.

        Args:
            ticker: Stock ticker symbol

        Returns:
            List of earnings surprise dicts, empty list on failure
        """
        try:
            data = self._make_request("stock/earnings", {"symbol": ticker})
            if not data or not isinstance(data, list):
                return []

            return [
                {
                    "date": earning.get("date"),
                    "actual": earning.get("actual"),
                    "estimate": earning.get("estimate"),
                    "surprise": earning.get("surprise"),
                    "surprise_percent": earning.get("surprisePercent"),
                }
                for earning in data
            ]
        except Exception as e:
            logger.error(f"Error getting earnings surprises for {ticker}: {e}")
            return []
