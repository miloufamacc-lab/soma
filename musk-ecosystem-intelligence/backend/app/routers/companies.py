"""
Companies router - Endpoints for company data and management.
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query

from app.ecosystem_data import (
    COMPANIES,
    get_company,
    get_relationships_for,
    search_companies,
    get_companies_by_type,
)

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("")
async def list_companies(
    type: Optional[str] = Query(None, description="Filter by company type (e.g., 'manufacturer', 'supplier', 'service_provider')"),
    sector: Optional[str] = Query(None, description="Filter by sector (e.g., 'automotive', 'energy', 'aerospace')"),
    search: Optional[str] = Query(None, description="Search by name or ticker"),
):
    """
    List all companies with optional filters.

    - **type**: Company type filter (supplier, manufacturer, service_provider, etc.)
    - **sector**: Industry sector filter (automotive, energy, aerospace, etc.)
    - **search**: Search by company name or ticker symbol

    Returns a list of company dictionaries with basic info.
    """
    companies = list(COMPANIES.values())

    # Apply search filter
    if search:
        search_lower = search.lower()
        companies = [
            c for c in companies
            if search_lower in c.get("name", "").lower()
            or search_lower in c.get("ticker", "").lower()
        ]

    # Apply type filter
    if type:
        companies = [c for c in companies if c.get("type") == type]

    # Apply sector filter
    if sector:
        companies = [c for c in companies if c.get("sector") == sector]

    return {
        "count": len(companies),
        "companies": companies,
    }


@router.get("/search")
async def search_companies_endpoint(q: str = Query(..., description="Search query (name or ticker)")):
    """
    Search companies by name or ticker.

    - **q**: Search query string (required)

    Returns matching companies.
    """
    if not q or len(q) < 2:
        raise HTTPException(status_code=400, detail="Search query must be at least 2 characters")

    results = search_companies(q)
    return {
        "query": q,
        "count": len(results),
        "results": results,
    }


@router.get("/{company_id}")
async def get_company_detail(company_id: str):
    """
    Get detailed information for a single company.

    Includes:
    - Basic company information
    - All relationships (suppliers, competitors, partners, etc.)
    - Recent news items
    - Financial snapshot (revenue, market cap, etc.)

    Returns 404 if company not found.
    """
    company = get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    # Get relationships
    relationships = get_relationships_for(company_id)

    # Build detail response
    detail = {
        **company,
        "relationships": relationships,
        "news_count": company.get("recent_news_count", 0),
        "news_items": company.get("recent_news", []),
        "financials": {
            "revenue_billions": company.get("revenue_billions"),
            "market_cap_billions": company.get("market_cap_billions"),
            "employees": company.get("employees"),
            "founded_year": company.get("founded_year"),
        },
    }

    return detail


@router.get("/{company_id}/relationships")
async def get_company_relationships(
    company_id: str,
    type: Optional[str] = Query(None, description="Filter by relationship type (supplier, competitor, partner, investor)"),
):
    """
    Get all relationships for a company.

    - **type**: Optional filter by relationship type (supplier, competitor, partner, investor, etc.)

    Returns a list of relationships with the connected company details.
    """
    company = get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    relationships = get_relationships_for(company_id)

    # Filter by type if specified
    if type:
        relationships = [r for r in relationships if r.get("type") == type]

    return {
        "company_id": company_id,
        "company_name": company.get("name"),
        "relationship_count": len(relationships),
        "relationships": relationships,
    }
