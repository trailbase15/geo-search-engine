from fastapi import FastAPI, Query
from geo_search.engine import get_engine, shutdown_engine, SearchRequest, CookieSpec
import httpx
import os

app = FastAPI(
    title="Geo Search Engine",
    description="Ultra-fast geospatial search with auto-cookie handling + automated places",
    version="0.1.0"
)

# Geoapify API Key (get free key from https://www.geoapify.com/get-started-with-maps-api)
GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY", "")

@app.on_event("startup")
async def startup():
    engine = get_engine()
    await engine.load_from_geojson("data/places.geojson")

@app.on_event("shutdown")
async def shutdown():
    await shutdown_engine()

# ─── Original Endpoints ───
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

# ─── DEBUG: Check if API key is loaded ───
@app.get("/geo/debug")
async def debug():
    key = GEOAPIFY_API_KEY
    return {
        "key_loaded": bool(key),
        "key_prefix": key[:8] + "..." if key else "NOT SET",
        "key_length": len(key) if key else 0,
        "env_vars": {k: v[:8] + "..." for k, v in os.environ.items() if "GEO" in k.upper() or "MAP" in k.upper() or "API" in k.upper()}
    }

# ─── DEBUG: Test Geoapify API directly ───
@app.get("/geo/debug/geoapify")
async def debug_geoapify(
    lat: float = Query(30.35886, ge=-90, le=90),
    lng: float = Query(73.3815, ge=-180, le=180),
    radius: int = Query(300, ge=50, le=5000)
):
    if not GEOAPIFY_API_KEY:
        return {"error": "No API key loaded"}
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.geoapify.com/v2/places",
                params={
                    "categories": "commercial,shop,office,catering,service,petrol",
                    "filter": f"circle:{lng},{lat},{radius}",
                    "limit": 20,
                    "apiKey": GEOAPIFY_API_KEY
                }
            )
        return {
            "status_code": resp.status_code,
            "data": resp.json() if resp.status_code == 200 else resp.text
        }
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}

# ─── NEW: Automated Places via Geoapify (Free 3000/day) ───
@app.get("/geo/auto")
async def auto_places(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius: int = Query(300, ge=50, le=5000)
):
    """
    Fully automated places - no manual curation needed.
    Uses Geoapify Places API (free 3000/day).
    Get free key: https://www.geoapify.com/get-started-with-maps-api
    """
    # 1. Try local curated data first
    engine = get_engine()
    local_results = await engine.search(SearchRequest(
        lat=lat, lng=lng, radius_m=radius
    ))
    if local_results:
        return {"source": "local", "results": local_results, "count": len(local_results)}
    
    # 2. Try Geoapify (if API key configured)
    if GEOAPIFY_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.geoapify.com/v2/places",
                    params={
                        "categories": "commercial,shop,office,catering,service,petrol",
                        "filter": f"circle:{lng},{lat},{radius}",
                        "limit": 50,
                        "apiKey": GEOAPIFY_API_KEY
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return transform_geoapify(data, lat, lng)
        except Exception as e:
            pass  # Fall through to local
    
    # 3. Return local results (even if empty)
    return {"source": "local", "results": local_results, "count": len(local_results)}

def transform_geoapify(data: dict, ref_lat: float, ref_lng: float):
    """Transform Geoapify response to our format."""
    results = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        coords = feature.get("geometry", {}).get("coordinates", [0, 0])
        lng, lat = coords[0], coords[1]
        
        # Calculate distance
        from math import radians, sin, cos, sqrt, atan2
        R = 6371000
        φ1, φ2 = radians(ref_lat), radians(lat)
        Δφ = radians(lat - ref_lat)
        Δλ = radians(lng - ref_lng)
        a = sin(Δφ/2)**2 + cos(φ1)*cos(φ2)*sin(Δλ/2)**2
        dist = 2 * R * atan2(sqrt(a), sqrt(1-a))
        
        results.append({
            "id": f"geoapify_{feature.get('properties',{}).get('place_id','')}",
            "name": props.get("name", "Unnamed"),
            "category": props.get("categories", ["poi"])[0].replace("_", " "),
            "lat": lat,
            "lng": lng,
            "distance_m": round(dist),
            "metadata": {
                "address": props.get("formatted", ""),
                "phone": props.get("contact", {}).get("phone", ""),
                "website": props.get("contact", {}).get("website", ""),
                "opening_hours": props.get("opening_hours", ""),
                "source": "geoapify"
            }
        })
    
    results.sort(key=lambda x: x["distance_m"])
    return {"source": "geoapify", "results": results[:50], "count": len(results)}

# ─── Camera Context (Enhanced with Geoapify) ───
@app.post("/geo/camera-context")
async def camera_context(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    heading: float = Query(None, ge=0, le=360),
    fov: float = Query(60, ge=10, le=180),
    radius_m: int = Query(300, ge=50, le=1000)
):
    """
    Camera-optimized search with bearing and in-frame detection.
    """
    engine = get_engine()
    raw = await engine.search(SearchRequest(
        lat=lat, lng=lng, radius_m=radius_m
    ))
    
    if not raw:
        # Try Geoapify as fallback
        if GEOAPIFY_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        "https://api.geoapify.com/v2/places",
                        params={
                            "categories": "commercial,shop,office,catering,service,petrol",
                            "filter": f"circle:{lng},{lat},{radius_m}",
                            "limit": 20,
                            "apiKey": GEOAPIFY_API_KEY
                        }
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        raw = transform_geoapify(data, lat, lng).get("results", [])
            except: pass
    
    if not raw:
        return {"primary": None, "nearby": []}
    
    primary = raw[0]
    
    # Add camera-relative bearing
    from math import radians, degrees, sin, cos, atan2
    for place in raw:
        bearing = calculate_bearing(lat, lng, place["lat"], place["lng"])
        place["bearing"] = round((bearing - (heading or 0)) % 360)
        place["in_frame"] = abs(place["bearing"]) < (fov / 2)
    
    return {
        "primary": {
            "id": primary["id"],
            "name": primary["name"],
            "category": primary["category"],
            "distance_m": primary["distance_m"],
            "bearing": round((calculate_bearing(lat, lng, primary["lat"], primary["lng"]) - (heading or 0)) % 360),
            "in_frame": abs((calculate_bearing(lat, lng, primary["lat"], primary["lng"]) - (heading or 0)) % 360) < (fov / 2),
            "metadata": primary.get("metadata", {})
        },
        "nearby": [
            {
                "id": p["id"],
                "name": p["name"],
                "category": p["category"],
                "distance_m": p["distance_m"],
                "bearing": p["bearing"],
                "in_frame": p["in_frame"]
            }
            for p in raw[1:6]
        ]
    }

def calculate_bearing(lat1, lng1, lat2, lng2):
    from math import radians, degrees, sin, cos, atan2
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlng = lng2 - lng1
    y = sin(dlng) * cos(lat2)
    x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlng)
    return (degrees(atan2(y, x)) + 360) % 360