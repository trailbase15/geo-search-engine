"""Geo Search Engine - Ultra-fast geospatial search with auto-cookie handling."""
from .engine import GeoSearchEngine, SearchRequest, SearchResult, CookieSpec, get_engine, shutdown_engine
from .models import GeoPoint

__version__ = "0.1.0"
__all__ = [
    "GeoSearchEngine",
    "SearchRequest",
    "SearchResult",
    "CookieSpec",
    "GeoPoint",
    "get_engine",
    "shutdown_engine",
]