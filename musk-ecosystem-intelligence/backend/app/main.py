"""
Main FastAPI application for Musk Ecosystem Intelligence.

Central orchestration file that handles:
- Router registration
- CORS middleware
- Static file serving
- Startup/shutdown events
- Health check endpoint
- Background scheduler for refresh tasks
"""

import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Import routers
from app.routers import companies, ecosystem, financials, news, economic

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Application metadata and initialization
app = FastAPI(
    title="Musk Ecosystem Intelligence",
    description="AI-powered intelligence platform for tracking the Musk company ecosystem",
    version="1.0.0"
)

# Global state for tracking uptime and cache
app_state = {
    "start_time": datetime.now(),
    "scheduler": None,
    "cache_stats": {
        "hits": 0,
        "misses": 0,
        "last_refresh": None
    }
}


# ============================================================================
# CORS Middleware
# ============================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info("CORS middleware configured for all origins (development mode)")


# ============================================================================
# Router Registration
# ============================================================================
app.include_router(companies.router)
app.include_router(ecosystem.router)
app.include_router(financials.router)
app.include_router(news.router)
app.include_router(economic.router)
logger.info("All routers registered successfully")


# ============================================================================
# Background Scheduler Jobs
# ============================================================================
def refresh_prices():
    """Background job to refresh company prices."""
    logger.info("Running scheduled price refresh job...")
    try:
        # TODO: Implement actual price refresh logic
        logger.debug("Price refresh completed")
        app_state["cache_stats"]["last_refresh"] = datetime.now()
    except Exception as e:
        logger.error(f"Error during price refresh: {e}")


def refresh_news():
    """Background job to refresh news data."""
    logger.info("Running scheduled news refresh job...")
    try:
        # TODO: Implement actual news refresh logic
        logger.debug("News refresh completed")
        app_state["cache_stats"]["last_refresh"] = datetime.now()
    except Exception as e:
        logger.error(f"Error during news refresh: {e}")


def refresh_financials():
    """Background job to refresh financial metrics."""
    logger.info("Running scheduled financial metrics refresh job...")
    try:
        # TODO: Implement actual financial metrics refresh logic
        logger.debug("Financial metrics refresh completed")
        app_state["cache_stats"]["last_refresh"] = datetime.now()
    except Exception as e:
        logger.error(f"Error during financial metrics refresh: {e}")


# ============================================================================
# Startup and Shutdown Events
# ============================================================================
@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    logger.info("=" * 80)
    logger.info("Musk Ecosystem Intelligence starting...")
    logger.info("=" * 80)

    # Initialize scheduler
    scheduler = BackgroundScheduler()

    # Schedule refresh jobs
    scheduler.add_job(
        refresh_prices,
        IntervalTrigger(minutes=5),
        id="refresh_prices",
        name="Refresh Company Prices",
        replace_existing=True
    )
    logger.info("Scheduled: Price refresh every 5 minutes")

    scheduler.add_job(
        refresh_news,
        IntervalTrigger(minutes=30),
        id="refresh_news",
        name="Refresh News",
        replace_existing=True
    )
    logger.info("Scheduled: News refresh every 30 minutes")

    scheduler.add_job(
        refresh_financials,
        IntervalTrigger(hours=2),
        id="refresh_financials",
        name="Refresh Financial Metrics",
        replace_existing=True
    )
    logger.info("Scheduled: Financial metrics refresh every 2 hours")

    # Start scheduler
    scheduler.start()
    app_state["scheduler"] = scheduler
    logger.info("APScheduler started successfully")

    # Initialize cache
    app_state["start_time"] = datetime.now()
    logger.info("Application cache initialized")
    logger.info("Musk Ecosystem Intelligence is ready")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Musk Ecosystem Intelligence shutting down...")

    # Stop scheduler
    if app_state["scheduler"]:
        app_state["scheduler"].shutdown()
        logger.info("APScheduler shutdown complete")

    logger.info("Cleanup completed")
    logger.info("=" * 80)


# ============================================================================
# Health Check Endpoint
# ============================================================================
@app.get("/api/health", status_code=status.HTTP_200_OK, tags=["Health"])
async def health_check():
    """
    Health check endpoint returning application status and metrics.

    Returns:
        - status: Application status (healthy/degraded/unhealthy)
        - uptime: Seconds since application startup
        - version: API version
        - timestamp: Current server timestamp
        - cache_stats: Cache hit/miss statistics
        - scheduler_status: Background scheduler status
    """
    uptime = (datetime.now() - app_state["start_time"]).total_seconds()
    scheduler_running = (
        app_state["scheduler"] and app_state["scheduler"].running
    )

    return {
        "status": "healthy",
        "uptime": uptime,
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "cache_stats": app_state["cache_stats"],
        "scheduler_status": "running" if scheduler_running else "stopped"
    }


# ============================================================================
# Static File Serving
# ============================================================================
# Determine frontend directory path
backend_dir = Path(__file__).parent.parent
frontend_dir = backend_dir.parent / "frontend"

if frontend_dir.exists():
    logger.info(f"Mounting static files from: {frontend_dir}")
    # Mount the frontend static files
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")
else:
    logger.warning(f"Frontend directory not found at: {frontend_dir}")


# ============================================================================
# Root Redirect to Frontend
# ============================================================================
@app.get("/", tags=["Frontend"])
async def serve_frontend():
    """
    Serve the frontend application at root path.

    Returns the index.html file from the frontend directory.
    """
    index_path = frontend_dir / "index.html"

    if index_path.exists():
        return FileResponse(index_path, media_type="text/html")
    else:
        # Return a simple message if frontend not available
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Musk Ecosystem Intelligence API",
                "version": "1.0.0",
                "docs": "/docs",
                "health": "/api/health"
            }
        )


# ============================================================================
# Error Handlers
# ============================================================================
@app.exception_handler(404)
async def not_found_exception_handler(request, exc):
    """Handle 404 Not Found errors."""
    logger.warning(f"404 Not Found: {request.url.path}")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "detail": "Resource not found",
            "path": request.url.path
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions (500 errors)."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "message": "An unexpected error occurred"
        }
    )


# ============================================================================
# Root Application Info
# ============================================================================
@app.get("/info", tags=["Info"])
async def application_info():
    """
    Get application information and available endpoints.

    Returns:
        - name: Application name
        - version: API version
        - description: Application description
        - uptime: Time since startup
        - documentation: Link to API documentation
    """
    uptime = (datetime.now() - app_state["start_time"]).total_seconds()

    return {
        "name": "Musk Ecosystem Intelligence",
        "version": "1.0.0",
        "description": "AI-powered intelligence platform for tracking the Musk company ecosystem",
        "uptime_seconds": uptime,
        "documentation": "/docs",
        "health_check": "/api/health",
        "available_routers": [
            "companies",
            "ecosystem",
            "financials",
            "news",
            "economic"
        ]
    }


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Musk Ecosystem Intelligence server...")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
