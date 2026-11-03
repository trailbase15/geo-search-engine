from fastapi import FastAPI
from geo_search.engine import get_engine, shutdown_engine, SearchRequest, CookieSpec

app = FastAPI(
    title="Geo Search Engine",
    description="Ultra-fast geospatial search with auto-cookie handling",
    version="0.1.0"
)

@app.on_event("startup")
async def startup():
    engine = get_engine()
    await engine.load_from_geojson("data/places.geojson")

@app.on_event("shutdown")
async def shutdown():
    await shutdown_engine()

@app.post("/geo/search")
async def search(req: SearchRequest):
    engine = get_engine()
    results = await engine.search(req)
    return {"results": results, "count": len(results)}

@app.post("/geo/cookies")
async def set_cookie(spec: CookieSpec):
    engine = get_engine()
    engine.set_cookie(spec)
    return {"ok": True}

@app.get("/geo/cookies/{domain}")
async def get_cookies(domain: str):
    engine = get_engine()
    return {"domain": domain, "cookie_header": engine.get_cookie_header(domain)}

@app.get("/geo/stats")
async def stats():
    engine = get_engine()
    return engine.stats()

@app.get("/health")
async def health():
    return {"status": "ok", "service": "geo-search-engine"}
