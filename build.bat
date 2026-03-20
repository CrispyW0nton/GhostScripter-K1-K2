@echo off
:: ================================================================
::  build.bat  —  GhostScripter-K1-K2  One-Click Build
:: ================================================================
::  Double-click this file OR right-click -> Run as administrator
::  if your antivirus blocks EXE creation.
::
::  Requirements:
::    - Python 3.10 or newer  (python.org/downloads)
::      Tick "Add Python to PATH" during install.
::
::  Everything else (PyQt5, PyInstaller, etc.) is installed
::  automatically into an isolated .venv folder.
:: ================================================================

:: Always run from the folder this bat lives in
cd /d "%~dp0"

echo.
echo  ============================================================
echo   GhostScripter-K1-K2  --  Build Script
echo  ============================================================
echo.

:: ----------------------------------------------------------------
:: STEP 1 — Find Python
:: ----------------------------------------------------------------
echo  [1/6] Looking for Python 3...

set "PY="
python --version >nul 2>&1
if not errorlevel 1 set "PY=python"

if not defined PY (
    py --version >nul 2>&1
    if not errorlevel 1 set "PY=py"
)

if not defined PY (
    echo.
    echo  ERROR: Python was not found.
    echo.
    echo  Install Python 3.10+ from:
    echo    https://www.python.org/downloads/
    echo.
    echo  During install tick:  Add Python to PATH
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%V in ('"%PY%" --version 2^>^&1') do echo  [OK] %%V found


:: ----------------------------------------------------------------
:: STEP 2 — Create virtual environment (once)
:: ----------------------------------------------------------------
echo.
echo  [2/6] Setting up virtual environment...

if not exist ".venv\Scripts\pip.exe" (
    echo       Creating .venv ...
    "%PY%" -m venv .venv
    if errorlevel 1 (
        echo.
        echo  ERROR: Could not create virtual environment.
        echo  Make sure "python -m venv" works on your machine.
        echo.
        pause
        exit /b 1
    )
    echo  [OK] .venv created.
) else (
    echo  [OK] .venv already exists, skipping creation.
)

:: Point directly at the venv's python/pip — no activate needed
set "VENV_PY=.venv\Scripts\python.exe"


:: ----------------------------------------------------------------
:: STEP 3 — Install dependencies
:: ----------------------------------------------------------------
echo.
echo  [3/6] Installing dependencies (first run takes 1-3 minutes)...
echo        pip, PyInstaller, PyQt5, Flask, SQLAlchemy ...
echo.

"%VENV_PY%" -m pip install --upgrade pip --quiet --quiet
"%VENV_PY%" -m pip install --upgrade pyinstaller --quiet --quiet
"%VENV_PY%" -m pip install --upgrade -r requirements.txt --quiet --quiet

if errorlevel 1 (
    echo.
    echo  ERROR: Dependency install failed.
    echo  Check your internet connection and try again.
    echo.
    pause
    exit /b 1
)
echo  [OK] All dependencies installed.


:: ----------------------------------------------------------------
:: STEP 4 — Generate icon (if missing)
:: ----------------------------------------------------------------
echo.
echo  [4/6] Checking application icon...

if not exist "resources\icons\ghostscripter.ico" (
    echo       Generating icon...
    "%VENV_PY%" build_tools\gen_icon.py 2>nul
    if errorlevel 1 (
        echo  [WARN] Icon generation failed - will build without custom icon.
    ) else (
        echo  [OK] Icon generated.
    )
) else (
    echo  [OK] Icon already present.
)


:: ----------------------------------------------------------------
:: STEP 5 — Clean old build output
:: ----------------------------------------------------------------
echo.
echo  [5/6] Cleaning previous build artefacts...
if exist dist  rmdir /s /q dist
if exist build rmdir /s /q build
echo  [OK] Clean.


:: ----------------------------------------------------------------
:: STEP 6 — Run PyInstaller
:: ----------------------------------------------------------------
echo.
echo  [6/6] Building GhostScripter-K1-K2.exe ...
echo        This takes 30-90 seconds. Window output will appear below.
echo.

"%VENV_PY%" -m PyInstaller --noconfirm ^
    --onefile ^
    --windowed ^
    --name "GhostScripter-K1-K2" ^
    --icon "resources\icons\ghostscripter.ico" ^
    --add-data "ghostscripter\ui\styles\dark.qss;ghostscripter/ui/styles" ^
    --add-data "resources\icons;resources/icons" ^
    --add-data "resources\scripts\k1\nwscript.nss;resources/scripts/k1" ^
    --add-data "resources\scripts\k2\nwscript.nss;resources/scripts/k2" ^
    --add-data "resources\tools\nwnnsscomp_k1.exe;resources/tools" ^
    --add-data "resources\tools\nwnnsscomp_k2.exe;resources/tools" ^
    --hidden-import "ghostscripter" ^
    --hidden-import "ghostscripter.core" ^
    --hidden-import "ghostscripter.core.twoda_manager" ^
    --hidden-import "ghostscripter.core.twoda_manager.twoda_manager" ^
    --hidden-import "ghostscripter.core.constants" ^
    --hidden-import "ghostscripter.core.database.manager" ^
    --hidden-import "ghostscripter.core.export.erf_writer" ^
    --hidden-import "ghostscripter.core.export.dlg_writer" ^
    --hidden-import "ghostscripter.core.export" ^
    --hidden-import "ghostscripter.core.resource_manager.resource_manager" ^
    --hidden-import "ghostscripter.core.nwscript" ^
    --hidden-import "ghostscripter.core.nwscript.parser" ^
    --hidden-import "ghostscripter.ipc.ghostrigger_bridge" ^
    --hidden-import "ghostscripter.ui.main_window" ^
    --hidden-import "ghostscripter.ui.widgets" ^
    --hidden-import "ghostscripter.ui.widgets.script_editor_widget" ^
    --hidden-import "ghostscripter.ui.widgets.dialogue_editor_widget" ^
    --hidden-import "ghostscripter.ui.widgets.quest_builder_widget" ^
    --hidden-import "ghostscripter.ui.widgets.twoda_manager_widget" ^
    --hidden-import "ghostscripter.ui.widgets.asset_library_widget" ^
    --hidden-import "ghostscripter.ui.widgets.tlk_editor_widget" ^
    --hidden-import "ghostscripter.ui.widgets.erf_packer_widget" ^
    --hidden-import "PyQt5" ^
    --hidden-import "PyQt5.QtCore" ^
    --hidden-import "PyQt5.QtGui" ^
    --hidden-import "PyQt5.QtWidgets" ^
    --hidden-import "PyQt5.QtNetwork" ^
    --hidden-import "PyQt5.sip" ^
    --hidden-import "PyQt5.QtPrintSupport" ^
    --hidden-import "flask" ^
    --hidden-import "werkzeug" ^
    --hidden-import "werkzeug.serving" ^
    --hidden-import "jinja2" ^
    --hidden-import "requests" ^
    --hidden-import "sqlalchemy" ^
    --hidden-import "sqlalchemy.dialects.sqlite" ^
    --hidden-import "sqlalchemy.pool" ^
    --hidden-import "sqlalchemy.orm" ^
    --hidden-import "_sqlite3" ^
    --hidden-import "sqlite3" ^
    --hidden-import "PIL" ^
    --hidden-import "PIL.Image" ^
    --hidden-import "PIL.ImageDraw" ^
    --hidden-import "PIL.ImageQt" ^
    --hidden-import "colorama" ^
    --exclude-module "tkinter" ^
    --exclude-module "matplotlib" ^
    --exclude-module "numpy" ^
    --exclude-module "pandas" ^
    --exclude-module "scipy" ^
    --exclude-module "pytest" ^
    --exclude-module "PyQt5.QtWebEngineWidgets" ^
    --exclude-module "PyQt5.QtWebEngineCore" ^
    --exclude-module "PyQt5.QtMultimedia" ^
    --exclude-module "PyQt5.QtSql" ^
    ghostscripter\main.py

if errorlevel 1 (
    echo.
    echo  ============================================================
    echo   ERROR: PyInstaller failed.
    echo.
    echo   Common fixes:
    echo     1. Antivirus blocking output — add project folder to AV
    echo        exclusions, delete build\ and dist\, then re-run.
    echo     2. Missing package — read the error above, then run:
    echo           .venv\Scripts\pip install ^<package-name^>
    echo        and re-run build.bat
    echo  ============================================================
    echo.
    pause
    exit /b 1
)


:: ----------------------------------------------------------------
:: Move EXE to root and clean up
:: ----------------------------------------------------------------
move /y "dist\GhostScripter-K1-K2.exe" "GhostScripter-K1-K2.exe" >nul
rmdir /s /q dist
rmdir /s /q build


:: ----------------------------------------------------------------
:: Done
:: ----------------------------------------------------------------
echo.
echo  ============================================================
echo   BUILD COMPLETE
echo.
echo   GhostScripter-K1-K2.exe  is in this folder.
echo   Double-click it to launch.
echo  ============================================================
echo.
pause
