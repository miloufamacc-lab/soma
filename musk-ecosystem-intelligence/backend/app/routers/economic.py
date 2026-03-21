"""
Economic router - Endpoints for economic indicators and macroeconomic data.
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/economic", tags=["economic"])


# Mock FRED economic indicators - in production, integrate with FRED API
MOCK_INDICATORS = {
    "SP500": {
        "series_id": "SP500",
        "title": "S&P 500 Index",
        "units": "Index Points",
        "latest_value": 5089.33,
        "latest_date": "2024-01-19",
        "change": 45.67,
        "change_percent": 0.91,
        "ecosystem_impact": "General market health affects all ecosystem companies",
        "historical_data": [
            {"date": "2024-01-19", "value": 5089.33},
            {"date": "2024-01-18", "value": 5043.66},
            {"date": "2024-01-17", "value": 5032.45},
            {"date": "2024-01-16", "value": 5019.23},
            {"date": "2024-01-15", "value": 5005.12},
        ],
    },
    "UNRATE": {
        "series_id": "UNRATE",
        "title": "Unemployment Rate",
        "units": "Percent",
        "latest_value": 3.7,
        "latest_date": "2024-01-01",
        "change": 0.1,
        "change_percent": 2.78,
        "ecosystem_impact": "Labor market tightness affects hiring and wage costs",
        "historical_data": [
            {"date": "2024-01-01", "value": 3.7},
            {"date": "2023-12-01", "value": 3.6},
            {"date": "2023-11-01", "value": 3.8},
            {"date": "2023-10-01", "value": 3.9},
            {"date": "2023-09-01", "value": 3.8},
        ],
    },
    "CPIAUCSL": {
        "series_id": "CPIAUCSL",
        "title": "Consumer Price Index for All Urban Consumers",
        "units": "Index Points",
        "latest_value": 312.35,
        "latest_date": "2024-01-01",
        "change": 2.45,
        "change_percent": 0.79,
        "ecosystem_impact": "Inflation affects input costs and consumer purchasing power",
        "historical_data": [
            {"date": "2024-01-01", "value": 312.35},
            {"date": "2023-12-01", "value": 309.90},
            {"date": "2023-11-01", "value": 307.05},
            {"date": "2023-10-01", "value": 306.75},
            {"date": "2023-09-01", "value": 304.50},
        ],
    },
    "DFF": {
        "series_id": "DFF",
        "title": "Federal Funds Effective Rate",
        "units": "Percent",
        "latest_value": 4.58,
        "latest_date": "2024-01-19",
        "change": -0.02,
        "change_percent": -0.44,
        "ecosystem_impact": "Interest rates affect borrowing costs and capital availability",
        "historical_data": [
            {"date": "2024-01-19", "value": 4.58},
            {"date": "2024-01-18", "value": 4.60},
            {"date": "2024-01-17", "value": 4.62},
            {"date": "2024-01-16", "value": 4.61},
            {"date": "2024-01-15", "value": 4.59},
        ],
    },
    "DCOILWTICO": {
        "series_id": "DCOILWTICO",
        "title": "West Texas Intermediate (WTI) Crude Oil Prices",
        "units": "Dollars per Barrel",
        "latest_value": 76.43,
        "latest_date": "2024-01-19",
        "change": 2.15,
        "change_percent": 2.89,
        "ecosystem_impact": "Oil prices affect energy costs and transportation/supply chain expenses",
        "historical_data": [
            {"date": "2024-01-19", "value": 76.43},
            {"date": "2024-01-18", "value": 74.28},
            {"date": "2024-01-17", "value": 73.45},
            {"date": "2024-01-16", "value": 72.90},
            {"date": "2024-01-15", "value": 72.15},
        ],
    },
}


@router.get("/indicators")
async def get_all_indicators():
    """
    Get all tracked economic indicators with their latest values.

    Returns a list of FRED indicators including:
    - Latest value and date
    - Change from previous period
    - Ecosystem impact narrative
    - Brief historical context

    Indicators tracked:
    - S&P 500 Index (SP500)
    - Unemployment Rate (UNRATE)
    - Consumer Price Index (CPIAUCSL)
    - Federal Funds Rate (DFF)
    - Oil Prices (DCOILWTICO)
    """
    indicators = []

    for series_id, data in MOCK_INDICATORS.items():
        indicators.append({
            "series_id": data.get("series_id"),
            "title": data.get("title"),
            "units": data.get("units"),
            "latest_value": data.get("latest_value"),
            "latest_date": data.get("latest_date"),
            "change": data.get("change"),
            "change_percent": data.get("change_percent"),
            "ecosystem_impact": data.get("ecosystem_impact"),
        })

    return {
        "count": len(indicators),
        "indicators": indicators,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/indicators/{series_id}")
async def get_specific_indicator(
    series_id: str,
    limit: int = Query(12, ge=1, le=120, description="Number of historical data points to return"),
):
    """
    Get a specific economic indicator with historical data.

    Parameters:
    - **series_id**: FRED series ID (e.g., SP500, UNRATE, CPIAUCSL, DFF, DCOILWTICO)
    - **limit**: Number of historical data points (default 12, max 120)

    Returns:
    - Indicator metadata
    - Latest value and change
    - Historical time series data
    - Ecosystem impact narrative
    """
    series_id_upper = series_id.upper()

    if series_id_upper not in MOCK_INDICATORS:
        raise HTTPException(
            status_code=404,
            detail=f"Indicator {series_id} not found. Available: {', '.join(MOCK_INDICATORS.keys())}",
        )

    data = MOCK_INDICATORS[series_id_upper]

    # Get historical data (limited by parameter)
    historical = data.get("historical_data", [])[:limit]

    return {
        "series_id": data.get("series_id"),
        "title": data.get("title"),
        "units": data.get("units"),
        "latest_value": data.get("latest_value"),
        "latest_date": data.get("latest_date"),
        "change": data.get("change"),
        "change_percent": data.get("change_percent"),
        "ecosystem_impact": data.get("ecosystem_impact"),
        "historical_data_points": len(historical),
        "historical_data": historical,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/dashboard")
async def get_economic_dashboard():
    """
    Get an economic dashboard summary with key indicators and ecosystem impact.

    Returns a curated summary of the most important economic indicators
    and narratives explaining their impact on the Musk ecosystem:
    - Market health (S&P 500, sector indices)
    - Employment and labor market
    - Inflation and price pressure
    - Interest rates and capital availability
    - Energy prices and supply chain
    - Overall economic outlook

    Useful for understanding macroeconomic context affecting the ecosystem.
    """
    # Select key indicators for dashboard
    key_indicators = ["SP500", "UNRATE", "CPIAUCSL", "DFF", "DCOILWTICO"]
    dashboard_data = []

    for series_id in key_indicators:
        if series_id in MOCK_INDICATORS:
            data = MOCK_INDICATORS[series_id]
            dashboard_data.append({
                "series_id": data.get("series_id"),
                "title": data.get("title"),
                "units": data.get("units"),
                "latest_value": data.get("latest_value"),
                "latest_date": data.get("latest_date"),
                "change_percent": data.get("change_percent"),
                "ecosystem_impact": data.get("ecosystem_impact"),
                "status": "positive" if data.get("change_percent", 0) >= 0 else "negative",
            })

    # Overall economic narrative
    overall_narrative = {
        "summary": "Economic conditions show mixed signals",
        "key_points": [
            "Stock market showing strength with S&P 500 near record highs",
            "Labor market remains tight with unemployment near 50-year lows",
            "Inflation moderating but still above Federal Reserve target",
            "Interest rates stable, providing relative affordability for capital projects",
            "Energy prices rising, increasing input costs across supply chain",
        ],
        "outlook": "Generally favorable for innovation and growth-oriented companies like those in the Musk ecosystem",
        "risks": [
            "Geopolitical tensions affecting commodity prices",
            "Potential future interest rate changes",
            "Supply chain vulnerabilities persisting",
        ],
    }

    return {
        "indicators": dashboard_data,
        "narrative": overall_narrative,
        "timestamp": datetime.now().isoformat(),
    }
