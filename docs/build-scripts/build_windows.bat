@echo off
REM Build script for Windows executable using PyInstaller
REM Usage: build_windows.bat

echo ========================================
echo Image Generation Test Tool - Windows Builder
echo ========================================
echo.

REM Check Python version
echo Checking Python version...
python --version
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    exit /b 1
)

REM Check if in correct directory
if not exist "cli.py" (
    echo ERROR: cli.py not found. Please run this script from the project root.
    exit /b 1
)

REM Install/upgrade PyInstaller
echo.
echo [1/4] Installing PyInstaller...
pip install --upgrade pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller
    exit /b 1
)

REM Install project dependencies
echo.
echo [2/4] Installing project dependencies...
pip install -e .[tui]
if errorlevel 1 (
    echo WARNING: Some dependencies may have failed to install
)

REM Clean previous build
echo.
echo [3/4] Cleaning previous build...
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist

REM Build with PyInstaller
echo.
echo [4/4] Building executable...
pyinstaller build_exe.spec --clean --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller build failed
    exit /b 1
)

echo.
echo ========================================
echo Build completed successfully!
echo ========================================
echo.
echo Output directory: dist\image-gen-test-tool\
echo Executables:
echo   - image-gen-test.exe  (CLI tool)
echo   - igt-tui.exe         (TUI interface)
echo.
echo To create a release package:
echo   1. Copy the entire dist\image-gen-test-tool\ folder
echo   2. Include .env.example and README.md
echo   3. Create ZIP archive for distribution
echo.

pause
