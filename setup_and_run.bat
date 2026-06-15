@echo off
setlocal EnableExtensions

:: Always run relative to this repository, even when launched by double-click.
cd /d "%~dp0"

set "ENV_NAME=Fastapp"
set "APP_URL=http://localhost:8000/static/index.html"

echo ==========================================
echo EDIS Setup and Run Script
echo ==========================================
echo [INFO] Project: %CD%
echo [INFO] Conda environment: %ENV_NAME%

:: 1. Locate Conda. `conda run -n NAME` works regardless of where the env lives.
set "CONDA_CMD="
where conda.exe >nul 2>nul
if %errorlevel% equ 0 set "CONDA_CMD=conda.exe"
if not defined CONDA_CMD if exist "%USERPROFILE%\anaconda3\condabin\conda.bat" set "CONDA_CMD=%USERPROFILE%\anaconda3\condabin\conda.bat"
if not defined CONDA_CMD if exist "%USERPROFILE%\miniconda3\condabin\conda.bat" set "CONDA_CMD=%USERPROFILE%\miniconda3\condabin\conda.bat"
if not defined CONDA_CMD if exist "C:\ProgramData\anaconda3\condabin\conda.bat" set "CONDA_CMD=C:\ProgramData\anaconda3\condabin\conda.bat"
if not defined CONDA_CMD if exist "C:\ProgramData\miniconda3\condabin\conda.bat" set "CONDA_CMD=C:\ProgramData\miniconda3\condabin\conda.bat"

if not defined CONDA_CMD (
    echo [ERROR] Conda was not found.
    echo Install Miniconda or Anaconda, then reopen this script.
    pause
    exit /b 1
)

:: 2. Create the environment when missing; otherwise update it from environment.yml.
echo [INFO] Checking Conda environment "%ENV_NAME%"...
call "%CONDA_CMD%" run -n "%ENV_NAME%" python --version >nul 2>nul
if errorlevel 1 (
    echo [INFO] Creating environment "%ENV_NAME%" from environment.yml. This may take a few minutes...
    call "%CONDA_CMD%" env create -f environment.yml
    if errorlevel 1 goto environment_error
) else (
    echo [INFO] Updating environment "%ENV_NAME%" from environment.yml...
    call "%CONDA_CMD%" env update -n "%ENV_NAME%" -f environment.yml
    if errorlevel 1 goto environment_error
)

:: 2b. Guarantee pip dependencies. `conda env update` does NOT reliably (re)install the
::     pip section, so install them explicitly here (idempotent / no-op if already present).
::     This prevents "import bcrypt/httpx fails -> app won't start / login fails".
echo [INFO] Ensuring pip dependencies are installed...
call "%CONDA_CMD%" run -n "%ENV_NAME%" python -m pip install -q "pulp>=2.7" "fastapi>=0.110" "uvicorn[standard]>=0.27" "pydantic>=2.0" "python-multipart>=0.0.9" "bcrypt>=4.0" "httpx>=0.24"
if errorlevel 1 goto environment_error

:: 3. Committed predictions.csv + model are enough to run. Rebuild only if missing.
if exist "data\processed\predictions.csv" if exist "models\xgboost_model.json" goto launch

echo [INFO] Model outputs are missing. The training pipeline must run once.
if not exist "data\raw\DataCoSupplyChainDataset.csv" if exist "data\raw\archive.zip" (
    echo [INFO] Extracting data\raw\archive.zip...
    powershell -NoProfile -Command "Expand-Archive -Path 'data\raw\archive.zip' -DestinationPath 'data\raw' -Force"
)
if not exist "data\raw\DataCoSupplyChainDataset.csv" (
    echo [ERROR] Missing model outputs AND raw dataset; cannot rebuild.
    echo Restore data\processed\predictions.csv + models\xgboost_model.json,
    echo or place DataCoSupplyChainDataset.csv into data\raw\ , then rerun.
    pause
    exit /b 1
)

echo [INFO] Rebuilding model outputs from raw data. This may take a few minutes...
call "%CONDA_CMD%" run --no-capture-output -n "%ENV_NAME%" python core\data_pipeline.py
if errorlevel 1 goto pipeline_error
call "%CONDA_CMD%" run --no-capture-output -n "%ENV_NAME%" python core\model_pipeline.py
if errorlevel 1 goto pipeline_error
call "%CONDA_CMD%" run --no-capture-output -n "%ENV_NAME%" python core\build_mappings.py

:launch
:: Optional: threshold tuning report instead of launching the server.
if /I "%~1"=="tune-threshold" (
    echo [INFO] Running threshold tuning report...
    call "%CONDA_CMD%" run --no-capture-output -n "%ENV_NAME%" python scripts\tune_threshold.py
    if errorlevel 1 (
        echo [ERROR] Threshold tuning failed.
        pause
        exit /b 1
    )
    echo [INFO] Threshold tuning completed.
    pause
    exit /b 0
)

:: Create/upgrade the local authentication database (admin/viewer, bcrypt).
echo [INFO] Initializing authentication database...
call "%CONDA_CMD%" run --no-capture-output -n "%ENV_NAME%" python core\auth.py
if errorlevel 1 (
    echo [ERROR] Authentication database initialization failed.
    pause
    exit /b 1
)

echo [INFO] Starting EDIS API server...
echo [INFO] Browser: %APP_URL%
echo [INFO] Press Ctrl+C to stop the server.
start "" "%APP_URL%"

call "%CONDA_CMD%" run --no-capture-output -n "%ENV_NAME%" python -m uvicorn app:app --host 127.0.0.1 --port 8000
if errorlevel 1 (
    echo.
    echo [ERROR] Server failed to start. Port 8000 may already be in use.
    echo Close the old server or run: netstat -ano ^| findstr :8000
    pause
    exit /b 1
)

exit /b 0

:environment_error
echo [ERROR] Failed to create/update the Conda environment or install dependencies.
echo Check your network connection and environment.yml, then try again.
pause
exit /b 1

:pipeline_error
echo [ERROR] Model training pipeline failed. See the messages above.
pause
exit /b 1
