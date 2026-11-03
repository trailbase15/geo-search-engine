"""FastAPI router for Geo Search Engine — mount in your main app."""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from .engine import GeoSearchEngine, SearchRequest, SearchResult, CookieSpec, get_engine

router = APIRouter(prefix="/geo", tags=["geosearch"])

class SearchResponse(BaseModel):
    query: SearchRequest
    results: List[SearchResult]
    count: int
    took_ms: float

class LoadResponse(BaseModel):
    loaded: int
    message: str

class CookieResponse(BaseModel):
    domain: str
    cookie_header: str

class StatsResponse(BaseModel):
    total_records: int
    h3_cells: int

@router.post("/search", response_model=SearchResponse, summary="Search nearby places")
async def search(
    req: SearchRequest,
    engine: GeoSearchEngine = Depends(get_engine)
):
    import time
    t0 = time.perf_counter()
    results = await engine.search(req)
    took = (time.perf_counter() - t0) * 1000
    return SearchResponse(query=req, results=results, count=len(results), took_ms=took)

@router.post("/load/geojson", response_model=LoadResponse, summary="Load data from GeoJSON")
async def load_geojson(
    path: str = Query(..., description="Path to GeoJSON file"),
    id_field: str = Query("id", description="Property field to use as ID"),
    engine: GeoSearchEngine = Depends(get_engine)
):
    count = await engine.load_from_geojson(path, id_field)
    return LoadResponse(loaded=count, message=f"Loaded {count} records from {path}")

@router.post("/load/json", response_model=LoadResponse, summary="Load data from JSON array")
async def load_json(
    path: str = Query(..., description="Path to JSON file"),
    engine: GeoSearchEngine = Depends(get_engine)
):
    count = await engine.load_from_json(path)
    return LoadResponse(loaded=count, message=f"Loaded {count} records from {path}")

@router.post("/cookies", summary="Set a cookie for a domain")
async def set_cookie(spec: CookieSpec, engine: GeoSearchEngine = Depends(get_engine)):
    engine.set_cookie(spec)
    return {"ok": True, "message": f"Cookie {spec.name} set for {spec.domain}"}

@router.post("/cookies/bulk", summary="Set multiple cookies for a domain")
async def set_cookies_bulk(
    domain: str = Query(..., description="Domain for cookies"),
    cookies: Dict[str, str] = Body(..., description="Cookie name-value pairs"),
    engine: GeoSearchEngine = Depends(get_engine)
):
    engine.set_cookies_from_dict(domain, cookies)
    return {"ok": True, "message": f"Set {len(cookies)} cookies for {domain}"}

@router.get("/cookies/{domain}", response_model=CookieResponse, summary="Get cookie header for domain")
async def get_cookies(domain: str, engine: GeoSearchEngine = Depends(get_engine)):
    return CookieResponse(domain=domain, cookie_header=engine.get_cookie_header(domain))

@router.get("/stats", response_model=StatsResponse, summary="Get engine statistics")
async def stats(engine: GeoSearchEngine = Depends(get_engine)):
    s = engine.stats()
    return StatsResponse(total_records=s.get("total_records", 0), h3_cells=s.get("h3_cells", 0))

@router.get("/health", summary="Health check")
async def health():
    return {"status": "ok", "service": "geo-search-engine"}