"""
FRED (Federal Reserve Economic Data) API client service.
Provides access to macroeconomic indicators relevant to the Musk ecosystem.
"""

import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class FREDService:
    """
    Client for FRED API (St. Louis Federal Reserve).

    Retrieves macroeconomic time series data and indicators.
    """

    # Pre-defined economic series relevant to Musk ecosystem
    INDICATORS = {
        "SP500": {"name": "S&P 500 Index", "category": "markets"},
        "VIXCLS": {"name": "VIX Volatility Index", "category": "markets"},
        "DFF": {"name": "Fed Funds Rate", "category": "interest_rates"},
        "DGS10": {"name": "10-Year Treasury Rate", "category": "interest_rates"},
        "CPIAUCSL": {"name": "Consumer Price Index", "category": "inflation"},
        "UNRATE": {"name": "Unemployment Rate", "category": "employment"},
        "A191RI1Q225SBEA": {"name": "Real GDP", "category": "economic_growth"},
        "INDPRO": {"name": "Industrial Production Index", "category": "production"},
        "DGORDER": {"name": "Durable Goods Orders", "category": "manufacturing"},
        "RSXFS": {"name": "Retail Sales", "category": "consumer"},
    }

    def __init__(self, api_key: Optional[str] = None, timeout: int = 10):
        """
        Initialize FRED service.

        Args:
            api_key: Optional FRED API key (not required for basic queries)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.base_url = "https://api.stlouisfed.org/fred"
        self.timeout = timeout

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Make a request to FRED API with error handling.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            Response JSON as dict, or None on failure
        """
        try:
            url = f"{self.base_url}/{endpoint}"
            request_params = params or {}

            # Add API key if provided
            if self.api_key:
                request_params["api_key"] = self.api_key

            response = requests.get(
                url,
                params=request_params,
                timeout=self.timeout,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"FRED API error for {endpoint}: {e}")
            return None
        except ValueError as e:
            logger.error(f"FRED JSON decode error for {endpoint}: {e}")
            return None

    def get_series(
        self,
        series_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get time series data for a FRED series.

        Args:
            series_id: FRED series identifier (e.g., 'SP500')
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Dict with series metadata and observations, or None on failure
        """
        try:
            params = {
                "series_id": series_id,
                "file_type": "json",
            }

            if start_date:
                params["observation_start"] = start_date
            if end_date:
                params["observation_end"] = end_date

            data = self._make_request("series/observations", params)
            if not data:
                return None

            return {
                "series_id": series_id,
                "title": self.INDICATORS.get(series_id, {}).get("name", series_id),
                "units": data.get("units"),
                "observations": [
                    {
                        "date": obs.get("date"),
                        "value": float(obs.get("value")) if obs.get("value") != "." else None,
                    }
                    for obs in data.get("observations", [])
                    if obs.get("value") != "."
                ],
                "count": len([obs for obs in data.get("observations", []) if obs.get("value") != "."]),
            }
        except Exception as e:
            logger.error(f"Error getting series {series_id}: {e}")
            return None

    def get_latest_value(self, series_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent observation for a series.

        Args:
            series_id: FRED series identifier

        Returns:
            Dict with date and value, or None on failure
        """
        try:
            series = self.get_series(series_id)
            if not series or not series.get("observations"):
                return None

            latest = series["observations"][-1]

            return {
                "series_id": series_id,
                "title": series.get("title"),
                "date": latest.get("date"),
                "value": latest.get("value"),
                "units": series.get("units"),
            }
        except Exception as e:
            logger.error(f"Error getting latest value for {series_id}: {e}")
            return None

    def get_all_indicators(self) -> Dict[str, Any]:
        """
        Get current values for all tracked economic indicators.

        Returns:
            Dict with indicator data for all series
        """
        results = {}

        for series_id in self.INDICATORS.keys():
            latest = self.get_latest_value(series_id)
            if latest:
                results[series_id] = latest
            else:
                logger.warning(f"Failed to fetch {series_id}")

        return {
            "timestamp": requests.get(
                f"{self.base_url}/series",
                params={"series_id": "SP500"},
                timeout=self.timeout,
            ).json().get("seriess", [{}])[0].get("lastUpdated"),
            "indicators": results,
            "count": len(results),
        }

    def get_indicator_narrative(self, series_id: str, value: Optional[float]) -> str:
        """
        Generate human-readable narrative about economic impact.

        Args:
            series_id: FRED series identifier
            value: Current value of the indicator

        Returns:
            Human-readable impact description
        """
        if value is None:
            return f"No data available for {series_id}"

        indicator = self.INDICATORS.get(series_id, {})
        title = indicator.get("name", series_id)
        category = indicator.get("category", "unknown")

        # Generate narratives based on category and value thresholds
        narratives = {
            "SP500": lambda v: (
                f"S&P 500 at {v:.0f}. "
                f"Strong market conditions may boost consumer confidence and increase Tesla demand."
                if v > 4500
                else f"S&P 500 at {v:.0f}. Market weakness could pressure EV stocks and reduce valuations."
            ),
            "VIXCLS": lambda v: (
                f"VIX at {v:.1f} (elevated volatility). "
                f"Market uncertainty may impact Tesla stock price and investor sentiment."
                if v > 20
                else f"VIX at {v:.1f} (low volatility). Stable market conditions support growth stocks."
            ),
            "DFF": lambda v: (
                f"Fed Funds Rate at {v:.2f}%. "
                f"Higher rates increase Tesla's borrowing costs for capital-intensive expansion."
                if v > 2.0
                else f"Fed Funds Rate at {v:.2f}%. Lower rates reduce financing costs for Tesla."
            ),
            "DGS10": lambda v: (
                f"10-Year Treasury at {v:.2f}%. "
                f"Rising long-term rates increase discount rates for Tesla's future cash flows."
                if v > 3.5
                else f"10-Year Treasury at {v:.2f}%. Lower yields make Tesla's growth narrative more attractive."
            ),
            "CPIAUCSL": lambda v: (
                f"Inflation at {v:.1f}%. "
                f"Rising inflation increases Tesla manufacturing costs and may pressure consumer demand."
                if v > 3.0
                else f"Inflation at {v:.1f}%. Controlled inflation supports stable business environment."
            ),
            "UNRATE": lambda v: (
                f"Unemployment at {v:.1f}%. "
                f"Higher joblessness reduces consumer demand for premium EV purchases."
                if v > 4.5
                else f"Unemployment at {v:.1f}%. Strong job market supports EV sales and consumer spending."
            ),
            "INDPRO": lambda v: (
                f"Industrial Production at {v:.1f}. "
                f"Strong manufacturing activity supports Tesla's production capabilities."
                if v > 105
                else f"Industrial Production at {v:.1f}. Weak manufacturing may indicate economic slowdown."
            ),
            "DGORDER": lambda v: (
                f"Durable Goods Orders at {v:.1f}B. "
                f"Strong orders indicate robust demand across manufacturing and tech sectors."
                if v > 250
                else f"Durable Goods Orders at {v:.1f}B. Weak orders suggest cautious business spending."
            ),
            "RSXFS": lambda v: (
                f"Retail Sales at {v:.1f}B. "
                f"Strong retail demand supports consumer spending on discretionary items like EVs."
                if v > 600
                else f"Retail Sales at {v:.1f}B. Weak retail sales indicate consumer caution."
            ),
        }

        if series_id in narratives:
            try:
                return narratives[series_id](value)
            except Exception as e:
                logger.error(f"Error generating narrative for {series_id}: {e}")

        return f"{title} at {value:.2f}. Impact on Musk ecosystem depends on broader economic context."

    def compare_indicators(
        self,
        series_ids: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get and compare multiple indicators.

        Args:
            series_ids: List of FRED series identifiers
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Dict with all series data for comparison
        """
        results = {}

        for series_id in series_ids:
            data = self.get_series(series_id, start_date, end_date)
            if data:
                results[series_id] = data

        return {
            "comparison_data": results,
            "count": len(results),
            "date_range": {"start": start_date, "end": end_date},
        }

    def get_correlation(self, series_id1: str, series_id2: str) -> Optional[float]:
        """
        Calculate correlation between two series (requires comparable time periods).

        Args:
            series_id1: First FRED series identifier
            series_id2: Second FRED series identifier

        Returns:
            Correlation coefficient (-1 to 1), or None on failure
        """
        try:
            import statistics

            data1 = self.get_series(series_id1)
            data2 = self.get_series(series_id2)

            if not data1 or not data2:
                return None

            obs1 = [o["value"] for o in data1.get("observations", []) if o["value"] is not None]
            obs2 = [o["value"] for o in data2.get("observations", []) if o["value"] is not None]

            if len(obs1) < 2 or len(obs2) < 2 or len(obs1) != len(obs2):
                return None

            mean1 = statistics.mean(obs1)
            mean2 = statistics.mean(obs2)

            numerator = sum((obs1[i] - mean1) * (obs2[i] - mean2) for i in range(len(obs1)))
            denom1 = sum((x - mean1) ** 2 for x in obs1) ** 0.5
            denom2 = sum((x - mean2) ** 2 for x in obs2) ** 0.5

            if denom1 == 0 or denom2 == 0:
                return None

            return numerator / (denom1 * denom2)

        except Exception as e:
            logger.error(f"Error calculating correlation: {e}")
            return None
