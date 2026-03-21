"""
News router - Endpoints for news feed and article search.
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query

from app.ecosystem_data import COMPANIES, get_company

router = APIRouter(prefix="/api/news", tags=["news"])


# Mock news data - in production, integrate with NewsAPI, ScraperAPI, etc.
MOCK_NEWS = [
    {
        "id": "news_001",
        "title": "Tesla Reports Record Q4 Deliveries",
        "source": "Reuters",
        "date": "2024-01-20",
        "category": "market",
        "sentiment": "positive",
        "companies": ["tesla"],
        "summary": "Tesla announced record vehicle deliveries in Q4, exceeding analyst expectations.",
        "url": "https://example.com/news/tesla-q4",
    },
    {
        "id": "news_002",
        "title": "NVIDIA Secures New Data Center Orders",
        "source": "TechCrunch",
        "date": "2024-01-19",
        "category": "market",
        "sentiment": "positive",
        "companies": ["nvidia"],
        "summary": "NVIDIA announces significant new orders from major cloud providers for its latest AI chips.",
        "url": "https://example.com/news/nvidia-orders",
    },
    {
        "id": "news_003",
        "title": "BYD Expands EV Production Capacity",
        "source": "Bloomberg",
        "date": "2024-01-18",
        "category": "market",
        "sentiment": "positive",
        "companies": ["byd"],
        "summary": "Chinese automaker BYD announces plans to expand electric vehicle manufacturing capacity.",
        "url": "https://example.com/news/byd-expansion",
    },
    {
        "id": "news_004",
        "title": "Supply Chain Disruptions Impact Electronics",
        "source": "Wall Street Journal",
        "date": "2024-01-17",
        "category": "supply_chain",
        "sentiment": "negative",
        "companies": ["nvidia", "apple"],
        "summary": "Global supply chain issues continue to affect semiconductor and electronics manufacturers.",
        "url": "https://example.com/news/supply-chain",
    },
    {
        "id": "news_005",
        "title": "Lucid Motors Secures Additional Funding",
        "source": "Forbes",
        "date": "2024-01-16",
        "category": "funding",
        "sentiment": "positive",
        "companies": ["lucid"],
        "summary": "Lucid Motors announces new funding round from Saudi PIF to accelerate production.",
        "url": "https://example.com/news/lucid-funding",
    },
]


@router.get("/ecosystem")
async def get_ecosystem_news(
    limit: int = Query(50, ge=1, le=200, description="Maximum number of news items to return"),
    category: Optional[str] = Query(None, description="Filter by category (market, supply_chain, funding, product, etc.)"),
    sentiment: Optional[str] = Query(None, description="Filter by sentiment (positive, negative, neutral)"),
):
    """
    Get aggregated news from the entire ecosystem.

    Aggregates news items from multiple sources related to all companies in the ecosystem.

    Parameters:
    - **limit**: Maximum number of news items (default 50, max 200)
    - **category**: Filter by news category (market, supply_chain, funding, product, etc.)
    - **sentiment**: Filter by sentiment (positive, negative, neutral)

    Returns news items sorted by recency.
    """
    news = list(MOCK_NEWS)

    # Apply category filter
    if category:
        news = [n for n in news if n.get("category") == category]

    # Apply sentiment filter
    if sentiment:
        news = [n for n in news if n.get("sentiment") == sentiment]

    # Sort by date (most recent first)
    news = sorted(news, key=lambda x: x.get("date", ""), reverse=True)

    # Apply limit
    news = news[:limit]

    return {
        "count": len(news),
        "limit": limit,
        "news": news,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/company/{company_id}")
async def get_company_news(
    company_id: str,
    limit: int = Query(50, ge=1, le=200, description="Maximum number of news items to return"),
):
    """
    Get news items related to a specific company.

    Returns all recent news, announcements, and market updates for the company.

    Parameters:
    - **limit**: Maximum number of news items (default 50, max 200)

    Returns 404 if company not found.
    """
    company = get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    company_name = company.get("name", "").lower()
    ticker = company.get("ticker", "").lower()

    # Filter news for this company
    company_news = [
        n for n in MOCK_NEWS
        if company_name in [c.lower() for c in n.get("companies", [])]
        or ticker in [c.lower() for c in n.get("companies", [])]
    ]

    # Sort by date (most recent first)
    company_news = sorted(company_news, key=lambda x: x.get("date", ""), reverse=True)

    # Apply limit
    company_news = company_news[:limit]

    # Add company recent news from knowledge base if available
    company_recent = company.get("recent_news", [])

    return {
        "company_id": company_id,
        "company_name": company.get("name"),
        "count": len(company_news),
        "news": company_news,
        "recent_from_kb": company_recent,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/trending")
async def get_trending_news(
    limit: int = Query(10, ge=1, le=50, description="Number of trending stories"),
):
    """
    Get the top trending news stories in the ecosystem.

    Trending is determined by recency and relevance to multiple ecosystem companies.

    Parameters:
    - **limit**: Number of trending stories (default 10, max 50)

    Returns top trending news items.
    """
    # For MVP, trending is just the most recent news items
    # In production, can add engagement metrics, mention frequency, etc.
    trending = sorted(MOCK_NEWS, key=lambda x: x.get("date", ""), reverse=True)[:limit]

    return {
        "count": len(trending),
        "trending": trending,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/search")
async def search_news(
    q: str = Query(..., description="Search query (article text, title, company name)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results"),
    category: Optional[str] = Query(None, description="Optional category filter"),
):
    """
    Search news articles by query string.

    Searches across article titles, summaries, and related companies.

    Parameters:
    - **q**: Search query (required)
    - **limit**: Maximum number of results (default 50, max 200)
    - **category**: Optional category filter

    Example: ?q=starlink&limit=20
    """
    if not q or len(q) < 2:
        raise HTTPException(status_code=400, detail="Search query must be at least 2 characters")

    query_lower = q.lower()

    # Search in title, summary, and companies
    results = [
        n for n in MOCK_NEWS
        if query_lower in n.get("title", "").lower()
        or query_lower in n.get("summary", "").lower()
        or any(query_lower in c.lower() for c in n.get("companies", []))
    ]

    # Apply category filter if specified
    if category:
        results = [n for n in results if n.get("category") == category]

    # Sort by date (most recent first)
    results = sorted(results, key=lambda x: x.get("date", ""), reverse=True)

    # Apply limit
    results = results[:limit]

    return {
        "query": q,
        "count": len(results),
        "results": results,
        "timestamp": datetime.now().isoformat(),
    }
