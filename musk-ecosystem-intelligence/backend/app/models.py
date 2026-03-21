"""
Pydantic models for the Musk Ecosystem Intelligence application.

This module defines all data models used throughout the application for
representing companies, relationships, financial data, market metrics, and
API responses.

Models are organized by category:
- Enums: Type definitions for categorical data
- Core Entity Models: Company, Relationship, and related entities
- Financial Models: Stock prices, financial metrics, economic indicators
- News and Analysis Models: Article data and sentiment analysis
- API Response Models: Structured responses for API endpoints
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, ConfigDict, validator


# ============================================================================
# ENUMS
# ============================================================================


class CompanyType(str, Enum):
    """Enumeration of company types within the ecosystem."""

    MUSK_OWNED = "musk_owned"
    SUPPLIER = "supplier"
    CUSTOMER = "customer"
    COMPETITOR = "competitor"
    PARTNER = "partner"
    GOVERNMENT = "government"
    INVESTOR = "investor"


class RelationshipType(str, Enum):
    """Enumeration of relationship types between companies."""

    SUPPLIER = "supplier"
    CUSTOMER = "customer"
    PARTNER = "partner"
    COMPETITOR = "competitor"
    SUBSIDIARY = "subsidiary"
    INVESTOR = "investor"
    TECHNOLOGY_PARTNER = "technology_partner"
    REGULATORY = "regulatory"
    GOVERNMENT_CONTRACT = "government_contract"


class Sector(str, Enum):
    """Enumeration of business sectors."""

    AUTOMOTIVE = "automotive"
    AEROSPACE = "aerospace"
    ENERGY = "energy"
    TECHNOLOGY = "technology"
    TELECOMMUNICATIONS = "telecommunications"
    FINANCE = "finance"
    MANUFACTURING = "manufacturing"
    MINING = "mining"
    SOFTWARE = "software"
    ENTERTAINMENT = "entertainment"
    INFRASTRUCTURE = "infrastructure"
    DEFENSE = "defense"
    GOVERNMENT = "government"
    VENTURE_CAPITAL = "venture_capital"
    OTHER = "other"


class CompanyStatus(str, Enum):
    """Enumeration of company status."""

    PUBLIC = "public"
    PRIVATE = "private"
    GOVERNMENT = "government"


class Sentiment(str, Enum):
    """Enumeration of sentiment analysis results."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class NewsCategory(str, Enum):
    """Enumeration of news article categories."""

    PRODUCT = "product"
    FINANCIAL = "financial"
    REGULATORY = "regulatory"
    PARTNERSHIP = "partnership"
    ACQUISITION = "acquisition"
    LEADERSHIP = "leadership"
    TECHNOLOGY = "technology"
    MARKET = "market"
    COMPETITOR = "competitor"
    GENERAL = "general"


# ============================================================================
# CORE ENTITY MODELS
# ============================================================================


class Company(BaseModel):
    """
    Represents a company within the Musk ecosystem.

    Attributes:
        id: Unique identifier for the company.
        name: Official company name.
        ticker: Stock ticker symbol (optional, for public companies).
        company_type: Type/role of the company in the ecosystem.
        sector: Business sector classification.
        description: Detailed description of the company and its operations.
        founded_year: Year the company was founded.
        headquarters: Location of headquarters.
        website: Company website URL.
        status: Public, private, or government entity status.
        market_cap: Market capitalization in USD (optional).
        employees: Number of employees (optional).
        logo_url: URL to company logo (optional).
        ceo: Chief Executive Officer name (optional).
    """

    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(..., description="Unique identifier for the company")
    name: str = Field(..., description="Official company name")
    ticker: Optional[str] = Field(
        None, description="Stock ticker symbol (for public companies)"
    )
    company_type: CompanyType = Field(..., description="Type of company in ecosystem")
    sector: Sector = Field(..., description="Business sector")
    description: str = Field(..., description="Company description")
    founded_year: Optional[int] = Field(None, description="Year company was founded")
    headquarters: str = Field(..., description="Headquarters location")
    website: Optional[str] = Field(None, description="Company website URL")
    status: CompanyStatus = Field(..., description="Company status")
    market_cap: Optional[float] = Field(
        None, description="Market capitalization in USD"
    )
    employees: Optional[int] = Field(None, description="Number of employees")
    logo_url: Optional[str] = Field(None, description="URL to company logo")
    ceo: Optional[str] = Field(None, description="Chief Executive Officer name")

    @validator("founded_year")
    def validate_founded_year(cls, v):
        """Validate that founded_year is reasonable."""
        if v is not None and (v < 1800 or v > datetime.now().year):
            raise ValueError("Founded year must be between 1800 and current year")
        return v

    @validator("market_cap")
    def validate_market_cap(cls, v):
        """Validate that market_cap is positive."""
        if v is not None and v < 0:
            raise ValueError("Market cap must be positive")
        return v

    @validator("employees")
    def validate_employees(cls, v):
        """Validate that employees count is positive."""
        if v is not None and v < 0:
            raise ValueError("Employee count must be positive")
        return v


class Relationship(BaseModel):
    """
    Represents a relationship between two companies.

    Attributes:
        id: Unique identifier for the relationship.
        source_id: ID of the source company.
        target_id: ID of the target company.
        relationship_type: Type of relationship.
        strength: Strength of relationship on a scale of 1-10.
        description: Description of the relationship.
        bidirectional: Whether the relationship is bidirectional.
        since_year: Year when relationship began (optional).
    """

    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(..., description="Unique identifier for the relationship")
    source_id: str = Field(..., description="ID of source company")
    target_id: str = Field(..., description="ID of target company")
    relationship_type: RelationshipType = Field(..., description="Type of relationship")
    strength: int = Field(
        ..., ge=1, le=10, description="Relationship strength (1-10 scale)"
    )
    description: str = Field(..., description="Description of the relationship")
    bidirectional: bool = Field(
        False, description="Whether relationship is bidirectional"
    )
    since_year: Optional[int] = Field(None, description="Year relationship began")

    @validator("since_year")
    def validate_since_year(cls, v):
        """Validate that since_year is reasonable."""
        if v is not None and (v < 1800 or v > datetime.now().year):
            raise ValueError("Since year must be between 1800 and current year")
        return v


# ============================================================================
# FINANCIAL MODELS
# ============================================================================


class StockPrice(BaseModel):
    """
    Represents current stock price information for a company.

    Attributes:
        ticker: Stock ticker symbol.
        current_price: Current trading price in USD.
        open_price: Opening price for the day.
        high: Highest price during the trading period.
        low: Lowest price during the trading period.
        volume: Trading volume.
        change_pct: Percentage change (as decimal, e.g., 2.5 for +2.5%).
        market_cap: Market capitalization in USD.
        pe_ratio: Price-to-earnings ratio (optional).
        timestamp: Time of the quote.
    """

    model_config = ConfigDict(use_enum_values=True)

    ticker: str = Field(..., description="Stock ticker symbol")
    current_price: float = Field(..., gt=0, description="Current trading price (USD)")
    open_price: float = Field(..., gt=0, description="Opening price for the day")
    high: float = Field(..., gt=0, description="Highest price in period")
    low: float = Field(..., gt=0, description="Lowest price in period")
    volume: int = Field(..., ge=0, description="Trading volume")
    change_pct: float = Field(..., description="Percentage change")
    market_cap: float = Field(..., gt=0, description="Market cap (USD)")
    pe_ratio: Optional[float] = Field(None, gt=0, description="Price-to-earnings ratio")
    timestamp: datetime = Field(..., description="Quote timestamp")

    @validator("high", "low", pre=False, always=True)
    def validate_high_low(cls, v, values):
        """Validate that high >= low and both are within reasonable range."""
        if "low" in values and "high" in values:
            if values["high"] < values["low"]:
                raise ValueError("High price must be >= low price")
        return v


class FinancialMetric(BaseModel):
    """
    Represents financial metrics for a company for a specific period.

    Attributes:
        company_id: ID of the company.
        revenue: Total revenue in USD.
        net_income: Net income in USD.
        gross_margin: Gross margin as percentage (0-100).
        operating_margin: Operating margin as percentage (0-100).
        debt_to_equity: Debt-to-equity ratio.
        current_ratio: Current ratio (current assets / current liabilities).
        roe: Return on equity as percentage.
        roa: Return on assets as percentage.
        free_cash_flow: Free cash flow in USD.
        period: Reporting period (e.g., "Q1 2024", "FY 2023").
        date: Date of the financial report.
        source: Source of the financial data.
    """

    model_config = ConfigDict(use_enum_values=True)

    company_id: str = Field(..., description="Company ID")
    revenue: Optional[float] = Field(None, ge=0, description="Total revenue (USD)")
    net_income: Optional[float] = Field(None, description="Net income (USD)")
    gross_margin: Optional[float] = Field(
        None, ge=0, le=100, description="Gross margin (%)"
    )
    operating_margin: Optional[float] = Field(
        None, ge=-100, le=100, description="Operating margin (%)"
    )
    debt_to_equity: Optional[float] = Field(None, ge=0, description="Debt-to-equity")
    current_ratio: Optional[float] = Field(None, gt=0, description="Current ratio")
    roe: Optional[float] = Field(None, description="Return on equity (%)")
    roa: Optional[float] = Field(None, description="Return on assets (%)")
    free_cash_flow: Optional[float] = Field(None, description="Free cash flow (USD)")
    period: str = Field(..., description="Reporting period")
    date: datetime = Field(..., description="Report date")
    source: str = Field(..., description="Data source")


class EconomicIndicator(BaseModel):
    """
    Represents macroeconomic indicators relevant to the ecosystem.

    Attributes:
        series_id: Unique identifier for the indicator series.
        name: Human-readable name of the indicator.
        description: Detailed description of what the indicator measures.
        value: Current value of the indicator.
        unit: Unit of measurement (e.g., "billion USD", "percent").
        date: Date when the indicator was measured.
        change_pct: Percentage change from previous period.
        affected_sectors: List of sectors affected by this indicator.
        narrative: Brief narrative explanation of the indicator and implications.
    """

    model_config = ConfigDict(use_enum_values=True)

    series_id: str = Field(..., description="Unique indicator series ID")
    name: str = Field(..., description="Indicator name")
    description: str = Field(..., description="Detailed description")
    value: float = Field(..., description="Current value")
    unit: str = Field(..., description="Unit of measurement")
    date: datetime = Field(..., description="Measurement date")
    change_pct: Optional[float] = Field(None, description="Percentage change")
    affected_sectors: List[str] = Field(
        default_factory=list, description="Affected sectors"
    )
    narrative: Optional[str] = Field(
        None, description="Narrative explanation and implications"
    )


# ============================================================================
# NEWS AND ANALYSIS MODELS
# ============================================================================


class NewsArticle(BaseModel):
    """
    Represents a news article relevant to the ecosystem.

    Attributes:
        id: Unique identifier for the article.
        title: Article headline.
        summary: Summary of the article content.
        source: News source name.
        source_url: URL to the original article.
        published_at: Publication timestamp.
        mentioned_companies: List of company IDs mentioned in the article.
        sentiment: Overall sentiment of the article.
        sentiment_score: Numerical sentiment score (-1.0 to 1.0).
        category: News category/topic.
        relevance_score: Relevance score to the ecosystem (0-1).
    """

    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(..., description="Unique article identifier")
    title: str = Field(..., description="Article headline")
    summary: str = Field(..., description="Article summary")
    source: str = Field(..., description="News source name")
    source_url: str = Field(..., description="URL to original article")
    published_at: datetime = Field(..., description="Publication timestamp")
    mentioned_companies: List[str] = Field(
        default_factory=list, description="Mentioned company IDs"
    )
    sentiment: Sentiment = Field(..., description="Sentiment analysis result")
    sentiment_score: float = Field(
        ..., ge=-1.0, le=1.0, description="Sentiment score (-1 to 1)"
    )
    category: NewsCategory = Field(..., description="Article category")
    relevance_score: float = Field(
        ..., ge=0, le=1, description="Relevance to ecosystem (0-1)"
    )


# ============================================================================
# API RESPONSE MODELS
# ============================================================================


class GraphNode(BaseModel):
    """
    Represents a node in the ecosystem graph (a company).

    Attributes:
        id: Company ID.
        label: Display name for the node.
        company_type: Type of company.
        sector: Business sector.
        market_cap: Market capitalization (optional).
        data: Additional metadata to display.
    """

    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(..., description="Company ID")
    label: str = Field(..., description="Display name")
    company_type: CompanyType = Field(..., description="Company type")
    sector: Sector = Field(..., description="Business sector")
    market_cap: Optional[float] = Field(None, description="Market cap")
    data: Dict[str, Any] = Field(default_factory=dict, description="Additional data")


class GraphEdge(BaseModel):
    """
    Represents an edge in the ecosystem graph (a relationship).

    Attributes:
        id: Relationship ID.
        source: Source company ID.
        target: Target company ID.
        relationship_type: Type of relationship.
        strength: Relationship strength (1-10).
        label: Display label for the edge.
    """

    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(..., description="Relationship ID")
    source: str = Field(..., description="Source company ID")
    target: str = Field(..., description="Target company ID")
    relationship_type: RelationshipType = Field(..., description="Relationship type")
    strength: int = Field(..., ge=1, le=10, description="Relationship strength")
    label: Optional[str] = Field(None, description="Display label")


class EcosystemGraphMetadata(BaseModel):
    """
    Metadata about the ecosystem graph.

    Attributes:
        total_companies: Total number of companies in the graph.
        total_relationships: Total number of relationships.
        generated_at: Timestamp when the graph was generated.
        data_sources: List of data sources used.
    """

    total_companies: int = Field(..., description="Total companies")
    total_relationships: int = Field(..., description="Total relationships")
    generated_at: datetime = Field(..., description="Generation timestamp")
    data_sources: List[str] = Field(
        default_factory=list, description="Data sources used"
    )


class EcosystemGraphResponse(BaseModel):
    """
    Complete ecosystem graph response.

    Attributes:
        nodes: List of company nodes.
        edges: List of relationship edges.
        metadata: Graph metadata.
    """

    nodes: List[GraphNode] = Field(..., description="Company nodes")
    edges: List[GraphEdge] = Field(..., description="Relationship edges")
    metadata: EcosystemGraphMetadata = Field(..., description="Graph metadata")


class CompanyDetailResponse(BaseModel):
    """
    Detailed response for a single company.

    Attributes:
        company: The company information.
        relationships: Companies this company is related to.
        financial_data: Recent financial metrics.
        stock_data: Current stock information (if public).
        recent_news: Recent news articles mentioning the company.
    """

    company: Company = Field(..., description="Company information")
    relationships: List[Relationship] = Field(
        default_factory=list, description="Related companies"
    )
    financial_data: List[FinancialMetric] = Field(
        default_factory=list, description="Financial metrics"
    )
    stock_data: Optional[StockPrice] = Field(
        None, description="Stock price data"
    )
    recent_news: List[NewsArticle] = Field(
        default_factory=list, description="Recent news"
    )


class MarketPulseResponse(BaseModel):
    """
    Market pulse summary response.

    Attributes:
        timestamp: When this pulse was generated.
        key_metrics: Key market metrics and their changes.
        trending_companies: Companies with significant recent activity.
        major_news: Major news items affecting the ecosystem.
        economic_indicators: Key economic indicators.
        sentiment_overview: Overall market sentiment.
    """

    timestamp: datetime = Field(..., description="Generation time")
    key_metrics: Dict[str, Any] = Field(
        default_factory=dict, description="Key metrics"
    )
    trending_companies: List[Company] = Field(
        default_factory=list, description="Trending companies"
    )
    major_news: List[NewsArticle] = Field(
        default_factory=list, description="Major news items"
    )
    economic_indicators: List[EconomicIndicator] = Field(
        default_factory=list, description="Economic indicators"
    )
    sentiment_overview: Dict[str, float] = Field(
        default_factory=dict, description="Sentiment by sector"
    )


class RelationshipAnalysisResponse(BaseModel):
    """
    Analysis of relationships for a specific company or relationship type.

    Attributes:
        center_company: The company at the center of analysis (optional).
        direct_relationships: First-degree relationships.
        indirect_relationships: Second-degree relationships.
        network_metrics: Network analysis metrics.
        summary: Text summary of findings.
    """

    center_company: Optional[Company] = Field(
        None, description="Center company"
    )
    direct_relationships: List[Relationship] = Field(
        default_factory=list, description="Direct relationships"
    )
    indirect_relationships: List[Dict[str, Any]] = Field(
        default_factory=list, description="Indirect relationships"
    )
    network_metrics: Dict[str, Any] = Field(
        default_factory=dict, description="Network metrics"
    )
    summary: str = Field(..., description="Analysis summary")


class SectorAnalysisResponse(BaseModel):
    """
    Analysis response for a specific sector.

    Attributes:
        sector: The sector being analyzed.
        companies: Companies in this sector.
        total_market_cap: Combined market cap of sector.
        key_relationships: Important relationships within the sector.
        trends: Current trends in the sector.
        opportunities: Potential opportunities identified.
    """

    sector: Sector = Field(..., description="Sector being analyzed")
    companies: List[Company] = Field(default_factory=list, description="Companies")
    total_market_cap: Optional[float] = Field(
        None, description="Total sector market cap"
    )
    key_relationships: List[Relationship] = Field(
        default_factory=list, description="Key relationships"
    )
    trends: List[str] = Field(default_factory=list, description="Trends")
    opportunities: List[str] = Field(
        default_factory=list, description="Opportunities"
    )


class NewsAnalysisResponse(BaseModel):
    """
    Analysis response for news and sentiment data.

    Attributes:
        period: Time period analyzed (e.g., "last 24 hours").
        total_articles: Total articles analyzed.
        sentiment_distribution: Distribution of sentiments.
        top_topics: Top topics discussed.
        company_mentions: Frequency of company mentions.
        sentiment_trend: Sentiment trend over time.
    """

    period: str = Field(..., description="Analysis period")
    total_articles: int = Field(..., description="Total articles analyzed")
    sentiment_distribution: Dict[str, int] = Field(
        default_factory=dict, description="Sentiment distribution"
    )
    top_topics: List[str] = Field(default_factory=list, description="Top topics")
    company_mentions: Dict[str, int] = Field(
        default_factory=dict, description="Company mention counts"
    )
    sentiment_trend: Dict[str, float] = Field(
        default_factory=dict, description="Sentiment trend"
    )


class PaginationMeta(BaseModel):
    """
    Pagination metadata for list responses.

    Attributes:
        total: Total number of items.
        page: Current page number.
        page_size: Number of items per page.
        total_pages: Total number of pages.
    """

    total: int = Field(..., description="Total items", ge=0)
    page: int = Field(..., description="Current page", ge=1)
    page_size: int = Field(..., description="Items per page", ge=1)
    total_pages: int = Field(..., description="Total pages", ge=0)


class PaginatedCompaniesResponse(BaseModel):
    """
    Paginated list of companies.

    Attributes:
        data: List of companies.
        pagination: Pagination metadata.
    """

    data: List[Company] = Field(..., description="Companies")
    pagination: PaginationMeta = Field(..., description="Pagination info")


class PaginatedNewsResponse(BaseModel):
    """
    Paginated list of news articles.

    Attributes:
        data: List of articles.
        pagination: Pagination metadata.
    """

    data: List[NewsArticle] = Field(..., description="News articles")
    pagination: PaginationMeta = Field(..., description="Pagination info")


class ErrorResponse(BaseModel):
    """
    Standard error response model.

    Attributes:
        error: Error code or name.
        message: Human-readable error message.
        details: Additional error details (optional).
        timestamp: When the error occurred.
    """

    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")
    timestamp: datetime = Field(..., description="Error timestamp")
