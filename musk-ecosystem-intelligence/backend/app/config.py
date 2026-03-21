"""
Configuration management for Musk Ecosystem Intelligence app.
Works out of the box with no API keys — just run it.
Add API keys later to get live data.
"""

import os

# Try to load .env file if it exists (totally optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Settings:
    """Application settings. All API keys are optional."""

    def __init__(self):
        # API Keys — all optional, app works without them using built-in data
        self.gurufocus_api_key = os.getenv("GURUFOCUS_API_KEY", "")
        self.finnhub_api_key = os.getenv("FINNHUB_API_KEY", "")
        self.fred_api_key = os.getenv("FRED_API_KEY", "")
        self.news_api_key = os.getenv("NEWS_API_KEY", "")

        # Server settings
        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "8000"))
        self.debug = os.getenv("DEBUG", "true").lower() == "true"

        # App metadata
        self.app_name = "Musk Ecosystem Intelligence"
        self.app_version = "1.0.0"


settings = Settings()
