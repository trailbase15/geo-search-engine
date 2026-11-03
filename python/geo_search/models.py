"""Pydantic models for Geo Search Engine."""
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List

class GeoPoint(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="Latitude in degrees")
    lng: float = Field(..., ge=-180, le=180, description="Longitude in degrees")

class SearchRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    radius_m: float = Field(5000, gt=0, le=50000, description="Search radius in meters")
    k: Optional[int] = Field(None, gt=0, le=100, description="K for KNN search")
    category: Optional[str] = Field(None, description="Filter by category")
    use_knn: bool = Field(False, description="Use KNN instead of radius search")

class SearchResult(BaseModel):
    id: str
    lat: float
    lng: float
    name: str
    category: str
    distance_m: float
    metadata: Dict[str, Any] = {}

class CookieSpec(BaseModel):
    name: str
    value: str
    domain: str
    path: str = "/"
    secure: bool = True
    http_only: bool = True

class BulkLoadRequest(BaseModel):
    records: List[Dict[str, Any]]
    id_field: str = "id"