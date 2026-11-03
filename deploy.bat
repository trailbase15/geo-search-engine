@echo off
REM deploy.bat — One-command deploy for Geo Search Engine on Windows
REM Usage: deploy.bat [target_dir]

setlocal enabledelayedexpansion

set TARGET_DIR=%~1
if "%TARGET_DIR%"=="" set TARGET_DIR=%USERPROFILE%\geo-search
set SCRIPT_DIR=%~dp0

echo 📦 Deploying Geo Search Engine to %TARGET_DIR%

REM Install Rust if needed
where cargo >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo 🦀 Installing Rust...
    curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs -o rustup-init.exe
    rustup-init.exe -y
    call "%USERPROFILE%\.cargo\env.bat"
)

REM Copy project
if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"
xcopy /E /I /Y "%SCRIPT_DIR%\*" "%TARGET_DIR%\"
cd /d "%TARGET_DIR%"

REM Build release wheel
echo 🔨 Building release wheel...
pip install maturin
maturin build --release --strip --out .\wheels

REM Install
echo 📥 Installing package...
for %%f in (wheels\*.whl) do pip install "%%f"

REM Verify
echo ✅ Verifying installation...
python -c "from geo_search.engine import GeoSearchEngine; print('Import OK')"
pytest tests\ -q

echo.
echo ✅ Deploy complete!
echo.
echo Add to your app:
echo   from geo_search.engine import get_engine
echo   engine = get_engine()
echo   await engine.load_from_geojson('data\places.geojson')
echo.
echo Mount FastAPI router:
echo   from geo_search.api import router as geo_router
echo   app.include_router(geo_router)

pause