# Dockerfile — Pure Python, no Rust needed
FROM python:3.11-slim

WORKDIR /app

# System deps (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY python/ ./python/
COPY data/ ./data/
COPY main.py .
COPY config.toml .

# Environment
ENV PYTHONPATH=/app/python
ENV PYTHONUNBUFFERED=1

# Port
EXPOSE 8000

# Run
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
