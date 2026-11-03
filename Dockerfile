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

@app

cd ~/Desktop/geo-search-engine

@"
# Dockerfile — Pure Python, no Rust needed
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY python/ ./python/
COPY data/ ./data/
COPY main.py .
COPY config.toml .

ENV PYTHONPATH=/app/python
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
