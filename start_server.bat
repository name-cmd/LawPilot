@echo off
title LawTrust - Server Launcher
cd /d "%~dp0"

echo ============================================
echo   LawTrust Chinese Legal AI - Server Launcher
echo   Default mode: DashScope API (no GPU needed)
echo ============================================
echo.

:: ============ 1. Check Python ============
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ or activate your conda env.
    pause
    exit /b 1
)

:: ============ 2. Check dependencies ============
echo [1/5] Checking dependencies...
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing dependencies, please wait...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Dependency install failed. Check network and requirements.txt.
        pause
        exit /b 1
    )
)
echo        Dependencies OK

:: ============ 3. Check knowledge base ============
echo [2/5] Checking knowledge base...
if not exist "law_db\chroma.sqlite3" (
    echo [INFO] Knowledge base not built yet. Building now (takes a few minutes)...
    python scripts/convert_md_to_json.py
    python scripts/build_knowledge_base.py
    if errorlevel 1 (
        echo [ERROR] Knowledge base build failed.
        pause
        exit /b 1
    )
)
echo        Knowledge base OK

:: ============ 4. Check API key ============
echo [3/5] Checking API key...
findstr /C:"DASHSCOPE_API_KEY=sk" .env >nul 2>&1
if errorlevel 1 (
    echo [WARN] DASHSCOPE_API_KEY not found in .env
    echo        Copy .env.example to .env and fill in your API key
    echo        (Alibaba DashScope console - API-KEY management)
    echo        Server still starts, but Q&A will report errors.
) else (
    echo        API key OK
)

:: ============ 5. Check local models ============
echo [4/5] Checking local models (RAG / NLI, CPU only)...
if not exist "models\bge-base-zh-v1.5\config.json" (
    echo [WARN] Embedding model missing: models\bge-base-zh-v1.5\
    echo        Required for legal retrieval. Q&A will not work without it.
)
if not exist "models\Erlangshen-Roberta-330M-NLI\config.json" (
    echo [WARN] NLI model missing: models\Erlangshen-Roberta-330M-NLI\
    echo        Used for citation verification. Feature will degrade.
)
echo        Model check done

:: ============ 6. Start server ============
echo [5/5] Starting server...
echo.
echo ============================================
echo   Server starting...
echo   Local access:  http://localhost:6006
echo   LAN access:    http://<your-lan-ip>:6006 (printed after startup)
echo   API docs:      http://localhost:6006/docs
echo   Press Ctrl+C to stop the server
echo ============================================
echo.

python scripts/run_server.py

pause
