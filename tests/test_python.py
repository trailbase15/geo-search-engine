"""Tests for Geo Search Engine Python API."""
import pytest
import asyncio
from geo_search.engine import GeoSearchEngine, SearchRequest


@pytest.fixture
def engine():
    eng = GeoSearchEngine()
    eng.load_records([
        {"id": "1", "lat": 31.5204, "lng": 74.3587, "name": "Liberty Market", "category": "food"},
        {"id": "2", "lat": 31.5500, "lng": 74.3500, "name": "Mall of Lahore", "category": "shopping"},
        {"id": "3", "lat": 31.5800, "lng": 74.3200, "name": "Shalimar Gardens", "category": "park"},
    ])
    return eng


@pytest.mark.asyncio
async def test_radius_search(engine):
    res = await engine.search(SearchRequest(lat=31.52, lng=74.36, radius_m=2000))
    assert len(res) == 1
    assert res[0].id == "1"


@pytest.mark.asyncio
async def test_knn_search(engine):
    res = await engine.search(SearchRequest(lat=31.52, lng=74.36, k=2, use_knn=True))
    assert len(res) == 2
    assert res[0].id == "1"


@pytest.mark.asyncio
async def test_category_filter(engine):
    res = await engine.search(SearchRequest(lat=31.55, lng=74.35, radius_m=5000, category="shopping"))
    assert len(res) == 1
    assert res[0].category == "shopping"


@pytest.mark.asyncio
async def test_cookie_jar(engine):
    engine.set_cookie("session", "abc123", "example.com", "/", True, True)
    assert engine.get_cookie("session") == "abc123"
    header = engine.get_cookie_header("example.com")
    assert "session=abc123" in header


@pytest.mark.asyncio
async def test_bulk_cookies(engine):
    engine.set_cookies_from_dict("api.example.com", {"a": "1", "b": "2"})
    header = engine.get_cookie_header("api.example.com")
    assert "a=1" in header and "b=2" in header


@pytest.mark.asyncio
async def test_haversine_accuracy(engine):
    # Distance between two known points ~3.5km
    res = await engine.search(SearchRequest(lat=31.5204, lng=74.3587, radius_m=4000))
    assert len(res) >= 1
    # First result should be the point itself (distance ~0)
    assert res[0].distance_m < 100


def test_engine_singleton():
    from geo_search.engine import get_engine, shutdown_engine
    import asyncio
    
    async def _test():
        e1 = get_engine()
        e2 = get_engine()
        assert e1 is e2
        await shutdown_engine()
    
    asyncio.run(_test())