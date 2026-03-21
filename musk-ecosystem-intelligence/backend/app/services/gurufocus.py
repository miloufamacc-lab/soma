"""
GuruFocus API client service for fundamental analysis.
Provides access to financial metrics, ratios, and institutional trades.
"""

import logging
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)


class GuruFocusService:
    """
    Client for GuruFocus API.

    Retrieves financial data, key ratios, and institutional trades.
    """

    def __init__(self, api_key: str, timeout: int = 10):
        """
        Initialize GuruFocus service.

        Args:
            api_key: GuruFocus API key
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.base_url = f"https://api.gurufocus.com/public/user/{api_key}"
        self.timeout = timeout

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Make a request to GuruFocus API with error handling.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            Response JSON as dict, or None on failure
        """
        try:
            url = f"{self.base_url}/{endpoint}"
            response = requests.get(
                url,
                params=params,
                timeout=self.timeout,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"GuruFocus API error for {endpoint}: {e}")
            return None
        except ValueError as e:
            logger.error(f"GuruFocus JSON decode error for {endpoint}: {e}")
            return None

    def get_financials(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get financial metrics for a stock.

        Args:
            ticker: Stock ticker symbol (e.g., 'TSLA')

        Returns:
            Dict with revenue, income, margins, ratios, or None on failure
        """
        try:
            data = self._make_request(f"stock/{ticker}/financials")
            if not data:
                return None

            # Extract relevant financial metrics
            return {
                "ticker": ticker,
                "revenue": data.get("revenue"),
                "net_income": data.get("net_income"),
                "operating_income": data.get("operating_income"),
                "gross_profit": data.get("gross_profit"),
                "gross_margin": data.get("gross_margin"),
                "operating_margin": data.get("operating_margin"),
                "net_margin": data.get("net_margin"),
                "ebitda": data.get("ebitda"),
                "free_cash_flow": data.get("free_cash_flow"),
                "timestamp": data.get("timestamp"),
            }
        except Exception as e:
            logger.error(f"Error getting financials for {ticker}: {e}")
            return None

    def get_key_ratios(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get key financial ratios for a stock.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with P/E, P/B, ROE, debt/equity, and other ratios, or None on failure
        """
        try:
            data = self._make_request(f"stock/{ticker}/key_ratios")
            if not data:
                return None

            return {
                "ticker": ticker,
                "pe_ratio": data.get("pe_ratio"),
                "pb_ratio": data.get("pb_ratio"),
                "ps_ratio": data.get("ps_ratio"),
                "peg_ratio": data.get("peg_ratio"),
                "roe": data.get("roe"),
                "roa": data.get("roa"),
                "roic": data.get("roic"),
                "debt_to_equity": data.get("debt_to_equity"),
                "debt_to_assets": data.get("debt_to_assets"),
                "current_ratio": data.get("current_ratio"),
                "quick_ratio": data.get("quick_ratio"),
                "interest_coverage": data.get("interest_coverage"),
                "timestamp": data.get("timestamp"),
            }
        except Exception as e:
            logger.error(f"Error getting key ratios for {ticker}: {e}")
            return None

    def get_stock_quote(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get current stock quote.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with price, volume, market cap, or None on failure
        """
        try:
            data = self._make_request(f"stock/{ticker}/quote")
            if not data:
                return None

            return {
                "ticker": ticker,
                "price": data.get("last"),
                "volume": data.get("volume"),
                "market_cap": data.get("market_cap"),
                "pe_ratio": data.get("pe_ratio"),
                "dividend_yield": data.get("dividend_yield"),
                "week_52_high": data.get("week_52_high"),
                "week_52_low": data.get("week_52_low"),
                "avg_volume": data.get("avg_volume"),
                "timestamp": data.get("timestamp"),
            }
        except Exception as e:
            logger.error(f"Error getting quote for {ticker}: {e}")
            return None

    def get_guru_trades(self, ticker: str, limit: int = 20) -> Optional[list]:
        """
        Get recent institutional trades (insider/guru trades).

        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of trades to return

        Returns:
            List of dicts with trade details, or None on failure
        """
        try:
            data = self._make_request(f"stock/{ticker}/guru_trades", {"limit": limit})
            if not data:
                return None

            trades = data.get("trades", [])
            return [
                {
                    "trader": trade.get("trader_name"),
                    "action": trade.get("action"),
                    "shares": trade.get("number_of_shares"),
                    "price": trade.get("price"),
                    "date": trade.get("date"),
                    "value": trade.get("value"),
                }
                for trade in trades
            ]
        except Exception as e:
            logger.error(f"Error getting guru trades for {ticker}: {e}")
            return None

    def get_rating(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get GuruFocus rating for a stock.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with rating, score, and analysis, or None on failure
        """
        try:
            data = self._make_request(f"stock/{ticker}/rating")
            if not data:
                return None

            return {
                "ticker": ticker,
                "rating": data.get("rating"),
                "score": data.get("score"),
                "valuation": data.get("valuation"),
                "growth": data.get("growth"),
                "profitability": data.get("profitability"),
                "momentum": data.get("momentum"),
                "financial_health": data.get("financial_health"),
            }
        except Exception as e:
            logger.error(f"Error getting rating for {ticker}: {e}")
            return None
