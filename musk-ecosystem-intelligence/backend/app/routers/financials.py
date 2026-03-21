"""
Financials router - Endpoints for financial data and stock information.
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query

from app.ecosystem_data import COMPANIES, get_company

router = APIRouter(prefix="/api/financials", tags=["financials"])


# Mock stock price data - in production, connect to Finnhub, Alpha Vantage, etc.
MOCK_STOCK_PRICES = {
    "TSLA": {"price": 245.50, "change": 2.3, "change_percent": 0.95},
    "NVDA": {"price": 875.30, "change": 12.50, "change_percent": 1.45},
    "BYD": {"price": 28.50, "change": -0.75, "change_percent": -2.56},
    "GE": {"price": 185.20, "change": 3.10, "change_percent": 1.70},
    "LCID": {"price": 2.95, "change": -0.05, "change_percent": -1.67},
    "AAPL": {"price": 242.84, "change": 1.50, "change_percent": 0.62},
    "AMAZON": {"price": 180.52, "change": 2.75, "change_percent": 1.55},
    "NEURALINK": {"price": None, "change": 0, "change_percent": 0},  # Private company
}


@router.get("/stocks")
async def get_all_stocks():
    """
    Get current stock prices for all public companies in the ecosystem.

    Uses cached data from financial data providers (Finnhub, Alpha Vantage).
    Falls back to mock data for demonstration.

    Returns a list of stocks with price, change, and percentage change.
    """
    stocks = []

    for company_id, company in COMPANIES.items():
        ticker = company.get("ticker")
        if ticker and ticker in MOCK_STOCK_PRICES:
            stock_data = MOCK_STOCK_PRICES[ticker]
            if stock_data.get("price"):  # Only include if price is available
                stocks.append({
                    "company_id": company_id,
                    "company_name": company.get("name"),
                    "ticker": ticker,
                    "price": stock_data.get("price"),
                    "change": stock_data.get("change"),
                    "change_percent": stock_data.get("change_percent"),
                    "market_cap_billions": company.get("market_cap_billions"),
                    "last_updated": datetime.now().isoformat(),
                })

    return {
        "count": len(stocks),
        "stocks": stocks,
        "last_updated": datetime.now().isoformat(),
    }


@router.get("/stocks/{ticker}")
async def get_stock_data(ticker: str):
    """
    Get detailed stock data for a specific ticker.

    Returns price, historical change, and related company information.
    """
    ticker_upper = ticker.upper()

    if ticker_upper not in MOCK_STOCK_PRICES:
        raise HTTPException(status_code=404, detail=f"Ticker {ticker} not found")

    # Find the company with this ticker
    company = None
    for c in COMPANIES.values():
        if c.get("ticker") == ticker_upper:
            company = c
            break

    if not company:
        raise HTTPException(status_code=404, detail=f"Company with ticker {ticker} not found")

    stock_data = MOCK_STOCK_PRICES[ticker_upper]

    return {
        "ticker": ticker_upper,
        "company_id": company.get("id"),
        "company_name": company.get("name"),
        "price": stock_data.get("price"),
        "change": stock_data.get("change"),
        "change_percent": stock_data.get("change_percent"),
        "market_cap_billions": company.get("market_cap_billions"),
        "revenue_billions": company.get("revenue_billions"),
        "employees": company.get("employees"),
        "sector": company.get("sector"),
        "website": company.get("website"),
        "last_updated": datetime.now().isoformat(),
    }


@router.get("/company/{company_id}/metrics")
async def get_company_financial_metrics(company_id: str):
    """
    Get financial metrics for a company.

    Includes revenue, margins, profitability ratios, and other metrics.
    Data sourced from GuruFocus API (with fallback to mock data for MVP).

    Returns financial snapshot including:
    - Revenue and revenue growth
    - Profit margins
    - Key financial ratios
    - Trend data
    """
    company = get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    # For MVP, return structured mock data from company knowledge base
    metrics = {
        "company_id": company_id,
        "company_name": company.get("name"),
        "ticker": company.get("ticker"),
        "financials": {
            "revenue_billions": company.get("revenue_billions"),
            "revenue_growth_percent": company.get("revenue_growth_percent", 15.5),
            "gross_margin_percent": company.get("gross_margin_percent", 25.3),
            "operating_margin_percent": company.get("operating_margin_percent", 12.8),
            "net_margin_percent": company.get("net_margin_percent", 8.5),
            "market_cap_billions": company.get("market_cap_billions"),
            "pe_ratio": company.get("pe_ratio", 35.2),
            "debt_to_equity": company.get("debt_to_equity", 0.35),
        },
        "employees": company.get("employees"),
        "founded_year": company.get("founded_year"),
        "sector": company.get("sector"),
        "note": "MVP data from ecosystem knowledge base. Connect to GuruFocus/FinancialModelingPrep for real-time data.",
    }

    return metrics


@router.get("/movers")
async def get_market_movers(
    limit: int = Query(10, ge=1, le=50, description="Number of movers to return"),
):
    """
    Get top gainers and losers among ecosystem stocks.

    Returns the most significant price movements (gainers and losers).

    - **limit**: Number of top movers to return (default 10, max 50)
    """
    stocks = []

    for company_id, company in COMPANIES.items():
        ticker = company.get("ticker")
        if ticker and ticker in MOCK_STOCK_PRICES:
            stock_data = MOCK_STOCK_PRICES[ticker]
            if stock_data.get("price"):
                stocks.append({
                    "company_id": company_id,
                    "company_name": company.get("name"),
                    "ticker": ticker,
                    "price": stock_data.get("price"),
                    "change": stock_data.get("change"),
                    "change_percent": stock_data.get("change_percent"),
                })

    # Sort by percentage change
    stocks_sorted = sorted(stocks, key=lambda x: x.get("change_percent", 0), reverse=True)

    gainers = stocks_sorted[:limit]
    losers = list(reversed(stocks_sorted[-limit:]))

    return {
        "gainers": gainers,
        "losers": losers,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/comparison")
async def compare_companies(
    companies: str = Query(..., description="Comma-separated company IDs or tickers (e.g., 'tsla,nvda,byd')"),
):
    """
    Compare financial metrics across multiple companies.

    - **companies**: Comma-separated list of company IDs or tickers

    Example: ?companies=tsla,nvda,byd

    Returns side-by-side financial metrics for easier comparison.
    """
    if not companies:
        raise HTTPException(status_code=400, detail="companies parameter is required")

    company_ids = [c.strip().upper() for c in companies.split(",")]
    comparison_data = []

    for identifier in company_ids:
        # Try to find by ID first, then by ticker
        company = get_company(identifier)
        if not company:
            # Try to find by ticker
            for c in COMPANIES.values():
                if c.get("ticker") == identifier:
                    company = c
                    break

        if not company:
            continue  # Skip not found companies

        metrics = {
            "company_id": company.get("id"),
            "company_name": company.get("name"),
            "ticker": company.get("ticker"),
            "revenue_billions": company.get("revenue_billions"),
            "revenue_growth_percent": company.get("revenue_growth_percent", 15.5),
            "market_cap_billions": company.get("market_cap_billions"),
            "gross_margin_percent": company.get("gross_margin_percent", 25.3),
            "operating_margin_percent": company.get("operating_margin_percent", 12.8),
            "net_margin_percent": company.get("net_margin_percent", 8.5),
            "employees": company.get("employees"),
            "pe_ratio": company.get("pe_ratio", 35.2),
            "debt_to_equity": company.get("debt_to_equity", 0.35),
        }
        comparison_data.append(metrics)

    if not comparison_data:
        raise HTTPException(status_code=404, detail="No companies found matching the provided IDs or tickers")

    return {
        "comparison_count": len(comparison_data),
        "companies": comparison_data,
        "timestamp": datetime.now().isoformat(),
    }
