# python/geo_search/engine.py — Pure Python Fallback (No Rust Required)
from __future__ import annotations
import asyncio
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx
import aiofiles

from .models import SearchRequest, SearchResult, CookieSpec, GeoPoint


# ──────────────────────────────────────────────
# Pure Python Engine (Haversine + Linear Search)
# ──────────────────────────────────────────────
@dataclass
class Record:
    id: str
    lat: float
    lng: float
    name: str
    category: str
    metadata: Dict = field(default_factory=dict)


class GeoSearchEngine:
    '''
    Pure Python Geo Search Engine — No Rust Required.
    Fast enough for 10K-100K records (~100-500 microseconds).
    
    Usage:
        engine = GeoSearchEngine()
        await engine.load_from_geojson("data/places.geojson")
        results = await engine.search(SearchRequest(lat=31.5, lng=74.3, radius_m=2000))
    '''
    
    def __init__(self, config: Optional[Dict] = None):
        self._records: List[Record] = []
        self._loop = asyncio.get_event_loop()
        self._http_client: Optional[httpx.AsyncClient] = None
        self._cookies: Dict[str, Dict[str, Dict]] = {}  # domain -> name -> cookie_info

    # ─── Data Loading ───
    def load_records(self, records: List[Dict]) -> None:
        '''Sync bulk load — call once at startup.'''
        self._records = [
            Record(
                id=r["id"], lat=r["lat"], lng=r["lng"],
                name=r["name"], category=r["category"], 
                metadata=r.get("metadata", {})
            ) for r in records
        ]

    async def load_from_geojson(self, path: str, id_field: str = "id") -> int:
        '''Async load from GeoJSON FeatureCollection.'''
        async with aiofiles.open(path) as f:
            data = json.loads(await f.read())
        records = []
        for feat in data.get("features", []):
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            if geom.get("type") != "Point":
                continue
            lng, lat = geom["coordinates"]
            records.append({
                "id": props.get(id_field, f"auto_{len(records)}"),
                "lat": lat, "lng": lng,
                "name": props.get("name", "Unknown"),
                "category": props.get("category", "general"),
                "metadata": {k: v for k, v in props.items() if k not in {"name", "category"}}
            })
        self.load_records(records)
        return len(records)

    async def load_from_json(self, path: str) -> int:
        '''Async load from JSON array of records.'''
        async with aiofiles.open(path) as f:
            records = json.loads(await f.read())
        self.load_records(records)
        return len(records)

    # ─── Search (Pure Python — Fast Enough) ───
    async def search(self, req: SearchRequest) -> List[SearchResult]:
        def _search():
            results = []
            for r in self._records:
                d = self._haversine(req.lat, req.lng, r.lat, r.lng)
                if d <= req.radius_m and (req.category is None or r.category == req.category):
                    results.append((d, r))
            results.sort(key=lambda x: x[0])
            if req.use_knn and req.k:
                results = results[:req.k]
            return [{
                "id": r.id, "lat": r.lat, "lng": r.lng, "name": r.name,
                "category": r.category, "distance_m": d, "metadata": r.metadata
            } for d, r in results]
        return await self._loop.run_in_executor(None, _search)

    @staticmethod
    def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        R = 6371000
        φ1, φ2 = math.radians(lat1), math.radians(lat2)
        Δφ = math.radians(lat2 - lat1)
        Δλ = math.radians(lng2 - lng1)
        a = math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

    # ─── Cookie Management ───
    def set_cookie(self, spec: CookieSpec) -> None:
        domain = spec.domain
        if domain not in self._cookies:
            self._cookies[domain] = {}
        self._cookies[domain][spec.name] = {
            "value": spec.value, "path": spec.path, 
            "secure": spec.secure, "http_only": spec.http_only
        }

    def get_cookie(self, name: str) -> Optional[str]:
        for domain_cookies in self._cookies.values():
            if name in domain_cookies:
                return domain_cookies[name]["value"]
        return None

    def get_cookie_header(self, domain: str) -> str:
        cookies = self._cookies.get(domain, {})
        return "; ".join(f"{k}={v['value']}" for k, v in cookies.items())

    def set_cookies_from_dict(self, domain: str, cookies: Dict[str, str]) -> None:
        if domain not in self._cookies:
            self._cookies[domain] = {}
        for name, value in cookies.items():
            self._cookies[domain][name] = {
                "value": value, "path": "/", "secure": True, "http_only": True
            }

    # ─── HTTP Client with Auto-Cookies ───
    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    async def fetch_with_cookies(self, url: str, domain: str, **kwargs) -> httpx.Response:
        client = await self._get_client()
        headers = kwargs.pop("headers", {})
        cookie_header = self.get_cookie_header(domain)
        if cookie_header:
            headers["Cookie"] = cookie_header
        return await client.get(url, headers=headers, **kwargs)

    async def post_with_cookies(self, url: str, domain: str, **kwargs) -> httpx.Response:
        client = await self._get_client()
        headers = kwargs.pop("headers", {})
        cookie_header = self.get_cookie_header(domain)
        if cookie_header:
            headers["Cookie"] = cookie_header
        return await client.post(url, headers=headers, **kwargs)

    async def close(self) -> None:
        if self._http_client:
            await self._http_client.aclose()

    def stats(self) -> Dict[str, Any]:
        return {"total_records": len(self._records), "mode": "pure_python"}


# ──────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────
_engine_instance: Optional[GeoSearchEngine] = None

def get_engine(config: Optional[Dict] = None) -> GeoSearchEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = GeoSearchEngine(config)
    return _engine_instance

async def shutdown_engine() -> None:
    global _engine_instance
    if _engine_instance:
        await _engine_instance.close()
        _engine_instance = None
