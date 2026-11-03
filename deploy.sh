#!/usr/bin/env bash
# deploy.sh — One-command deploy for Geo Search Engine
# Usage: ./deploy.sh [target_dir]

set -euo pipefail

TARGET_DIR="${1:-/opt/geo-search}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "📦 Deploying Geo Search Engine to $TARGET_DIR"

# Install Rust if needed
if ! command -v cargo &> /dev/null; then
    echo "🦀 Installing Rust..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
fi

# Copy project
mkdir -p "$TARGET_DIR"
cp -r "$SCRIPT_DIR"/* "$TARGET_DIR/"
cd "$TARGET_DIR"

# Build release wheel
echo "🔨 Building release wheel..."
pip install maturin
maturin build --release --strip --out ./wheels

# Install
echo "📥 Installing package..."
pip install ./wheels/*.whl

# Verify
echo "✅ Verifying installation..."
python -c "from geo_search.engine import GeoSearchEngine; print('Import OK')"
pytest tests/ -q

echo ""
echo "✅ Deploy complete!"
echo ""
echo "Add to your app:"
echo "  from geo_search.engine import get_engine"
echo "  engine = get_engine()"
echo "  await engine.load_from_geojson('data/places.geojson')"
echo ""
echo "Mount FastAPI router:"
echo "  from geo_search.api import router as geo_router"
echo "  app.include_router(geo_router)"