"""
HORIZON Analytical Lenses — 7-lens tactical timing engine.
Pipeline: SOMA/HORIZON | Module: SOMA | Status: ALL 7 LENSES BUILT

Each lens reads from SOMA data layer and/or live web sources,
produces a standardized LensResult with directional signal and confidence.

Lenses (Grok Expert-mode weights, cross-AI reviewed):
    MACRO           35%   Regime gate + GLI + components
    BTC_ONCHAIN     12%   NVT, MVRV, SOPR, exchange flows, MSTR NAV
    CREDIT_LIQUIDITY 10%  IG/HY spreads, VRP, TED, MM flows
    FUNDAMENTAL     15%   Fair value, execution score, valuation trend
    TECHNICAL       12%   Momentum, volatility regime, drawdown, MAs
    SENTIMENT        9%   News, analyst consensus, options flow, insider
    GEOPOLITICAL     7%   FOMC/CPI calendar, regulatory, market structure
"""

# Phase 1 lenses
from .macro_lens import MacroLens
from .fundamental_lens import FundamentalLens
from .technical_lens import TechnicalLens

# Phase 2 lenses
from .btc_onchain_lens import BtcOnchainLens
from .credit_liquidity_lens import CreditLiquidityLens
from .sentiment_lens import SentimentLens
from .event_lens import EventLens

__all__ = [
    "MacroLens",
    "FundamentalLens",
    "TechnicalLens",
    "BtcOnchainLens",
    "CreditLiquidityLens",
    "SentimentLens",
    "EventLens",
]
