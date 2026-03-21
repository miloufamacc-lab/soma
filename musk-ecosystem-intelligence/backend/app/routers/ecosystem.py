"""
Ecosystem router - Endpoints for ecosystem intelligence and network analysis.
"""
from typing import List, Optional, Dict, Set
from fastapi import APIRouter, HTTPException, Query

from app.ecosystem_data import (
    COMPANIES,
    RELATIONSHIPS,
    get_company,
    get_relationships_for,
    get_ecosystem_graph,
)

router = APIRouter(prefix="/api/ecosystem", tags=["ecosystem"])


@router.get("/graph")
async def get_ecosystem_graph_endpoint(
    types: Optional[str] = Query(None, description="Comma-separated relationship types to include (supplier,competitor,partner)"),
):
    """
    Get the full ecosystem graph data formatted for D3.js visualization.

    Returns nodes and edges suitable for network visualization:
    - **nodes**: Company nodes with type, market_cap for sizing, sector, etc.
    - **edges**: Relationship edges with type and strength

    Optional:
    - **types**: Filter edges by relationship types (comma-separated)

    Example: ?types=supplier,competitor
    """
    graph = get_ecosystem_graph()
    links = graph.get("links", [])

    # Filter by relationship types if specified
    if types:
        allowed_types = set(t.strip() for t in types.split(","))
        links = [e for e in links if e.get("type") in allowed_types]

    return {
        "node_count": len(graph.get("nodes", [])),
        "edge_count": len(links),
        "nodes": graph.get("nodes", []),
        "edges": links,
    }


@router.get("/company/{company_id}/connections")
async def get_company_connections(
    company_id: str,
    depth: int = Query(2, ge=1, le=5, description="Search depth (1-5 levels of connections)"),
):
    """
    Get direct and indirect connections for a company up to specified depth.

    Uses breadth-first search to find all connected companies up to the specified depth.

    - **depth**: Number of connection levels to include (default 2, max 5)

    Returns a subgraph with the company and all its connections.
    """
    company = get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    # BFS to find all connections up to depth N
    visited = set()
    current_level = {company_id}
    connections_by_depth = {}

    for d in range(1, depth + 1):
        next_level = set()
        connections_by_depth[d] = []

        for cid in current_level:
            relationships = get_relationships_for(cid)
            for rel in relationships:
                connected_id = rel.get("target_id") if rel.get("source_id") == cid else rel.get("source_id")
                if connected_id and connected_id not in visited:
                    next_level.add(connected_id)
                    visited.add(connected_id)
                    connections_by_depth[d].append({
                        "company_id": connected_id,
                        "company_name": get_company(connected_id).get("name") if get_company(connected_id) else None,
                        "relationship_type": rel.get("relationship_type", rel.get("type")),
                        "depth": d,
                    })

        current_level = next_level
        if not current_level:
            break

    return {
        "company_id": company_id,
        "company_name": company.get("name"),
        "total_connections": len(visited),
        "connections_by_depth": connections_by_depth,
    }


@router.get("/company/{company_id}/influence")
async def get_company_influence(company_id: str):
    """
    Calculate influence score for a company based on connections.

    Influence is determined by:
    - Number of direct connections
    - Strength of connections (weighted by relationship type)
    - Types of companies connected

    Returns influence score (0-100) and breakdown by connection type.
    """
    company = get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    relationships = get_relationships_for(company_id)

    # Weight different relationship types
    type_weights = {
        "investor": 1.5,
        "partner": 1.2,
        "supplier": 1.0,
        "customer": 1.0,
        "competitor": 0.8,
    }

    influence_score = 0
    breakdown = {
        "supplier": 0,
        "customer": 0,
        "partner": 0,
        "competitor": 0,
        "investor": 0,
    }

    for rel in relationships:
        rel_type = rel.get("type", "supplier")
        weight = type_weights.get(rel_type, 1.0)
        strength = rel.get("strength", 0.5)
        influence_score += weight * strength * 10  # Scale to reasonable range

        if rel_type in breakdown:
            breakdown[rel_type] += 1

    # Normalize to 0-100 scale
    influence_score = min(100, influence_score)

    return {
        "company_id": company_id,
        "company_name": company.get("name"),
        "influence_score": round(influence_score, 2),
        "total_connections": len(relationships),
        "breakdown_by_type": breakdown,
        "connected_entities": [
            {
                "id": (rel.get("target_id") if rel.get("source_id") == company_id else rel.get("source_id")),
                "name": get_company(rel.get("target_id") if rel.get("source_id") == company_id else rel.get("source_id")).get("name"),
                "type": rel.get("relationship_type", rel.get("type")),
                "strength": rel.get("strength"),
            }
            for rel in relationships
        ],
    }


@router.get("/supply-chain/{company_id}")
async def trace_supply_chain(company_id: str):
    """
    Trace the supply chain for a company (upstream suppliers and downstream customers).

    Returns the supply chain as an ordered list showing:
    - Upstream suppliers (and their suppliers)
    - The company itself
    - Downstream customers

    Example: Company -> Supplier A -> Supplier B (upstream), Company -> Customer X (downstream)
    """
    company = get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    relationships = get_relationships_for(company_id)

    # Separate suppliers and customers
    suppliers = []
    customers = []

    for rel in relationships:
        if rel.get("relationship_type", rel.get("type")) == "supplier":
            connected_id = rel.get("source_id") if rel.get("target_id") == company_id else rel.get("target_id")
            supplier_company = get_company(connected_id)
            suppliers.append({
                "company_id": connected_id,
                "company_name": supplier_company.get("name") if supplier_company else None,
                "strength": rel.get("strength"),
            })
        elif rel.get("relationship_type", rel.get("type")) == "customer":
            connected_id = rel.get("source_id") if rel.get("target_id") == company_id else rel.get("target_id")
            customer_company = get_company(connected_id)
            customers.append({
                "company_id": connected_id,
                "company_name": customer_company.get("name") if customer_company else None,
                "strength": rel.get("strength"),
            })

    return {
        "company_id": company_id,
        "company_name": company.get("name"),
        "upstream_suppliers": suppliers,
        "downstream_customers": customers,
        "total_suppliers": len(suppliers),
        "total_customers": len(customers),
    }


@router.get("/stats")
async def get_ecosystem_stats():
    """
    Get ecosystem statistics and summary metrics.

    Returns:
    - Total number of companies
    - Total relationships
    - Breakdown by relationship type
    - Most connected companies
    - Average connections per company
    - Sectors represented
    """
    total_companies = len(COMPANIES)
    total_relationships = len(RELATIONSHIPS)

    # Count relationships by type
    rel_by_type = {}
    for rel in RELATIONSHIPS:
        rel_type = rel.get("relationship_type", rel.get("type", "unknown"))
        rel_by_type[rel_type] = rel_by_type.get(rel_type, 0) + 1

    # Find most connected companies
    connection_counts = {}
    for rel in RELATIONSHIPS:
        source = rel.get("source_id")
        target = rel.get("target_id")
        connection_counts[source] = connection_counts.get(source, 0) + 1
        connection_counts[target] = connection_counts.get(target, 0) + 1

    most_connected = sorted(
        [(cid, count) for cid, count in connection_counts.items()],
        key=lambda x: x[1],
        reverse=True,
    )[:5]

    most_connected_data = [
        {
            "company_id": cid,
            "company_name": get_company(cid).get("name") if get_company(cid) else None,
            "connection_count": count,
        }
        for cid, count in most_connected
    ]

    # Calculate average connections
    avg_connections = total_relationships * 2 / total_companies if total_companies > 0 else 0

    # Count sectors
    sectors = {}
    for company in COMPANIES.values():
        sector = company.get("sector", "Unknown")
        sectors[sector] = sectors.get(sector, 0) + 1

    return {
        "total_companies": total_companies,
        "total_relationships": total_relationships,
        "relationships_by_type": rel_by_type,
        "average_connections_per_company": round(avg_connections, 2),
        "most_connected_companies": most_connected_data,
        "sectors": sectors,
    }
