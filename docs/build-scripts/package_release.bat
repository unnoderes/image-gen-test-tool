@echo off
REM Package release script for Windows
REM Creates a distributable ZIP package with executables and documentation

set VERSION=0.1.0
set PACKAGE_NAME=image-gen-test-tool-windows-v%VERSION%

echo ========================================
echo Packaging Release for Windows
echo ========================================
echo.

REM Check if build exists
if not exist "dist\image-gen-test-tool\image-gen-test.exe" (
    echo ERROR: Build not found. Please run build_windows.bat first.
    exit /b 1
)

REM Create package directory
echo [1/4] Creating package directory...
if exist "%PACKAGE_NAME%" rmdir /s /q "%PACKAGE_NAME%"
mkdir "%PACKAGE_NAME%"

REM Copy executables
echo [2/4] Copying executables...
xcopy /s /e /q "dist\image-gen-test-tool" "%PACKAGE_NAME%\"

REM Copy documentation
echo [3/4] Copying documentation...
copy "README.md" "%PACKAGE_NAME%\"
copy ".env.example" "%PACKAGE_NAME%\"
copy "custom_models.json" "%PACKAGE_NAME%\"
if exist "docs" xcopy /s /e /q "docs" "%PACKAGE_NAME%\docs\"

REM Create quick start guide
echo [4/4] Creating quick start guide...
(
echo Image Generation Test Tool v%VERSION% - Windows Release
echo.
echo Quick Start:
echo 1. Copy .env.example to .env
echo 2. Edit .env and add your API keys
echo 3. Run:
echo    - image-gen-test.exe --help ^(CLI tool^)
echo    - igt-tui.exe            ^(TUI interface^)
echo.
echo For detailed documentation, see README.md and docs\
echo.
echo Project: https://github.com/yourusername/image-gen-test-tool
) > "%PACKAGE_NAME%\QUICKSTART.txt"

REM Create ZIP
echo.
echo Creating ZIP archive...
powershell -Command "Compress-Archive -Path '%PACKAGE_NAME%' -DestinationPath '%PACKAGE_NAME%.zip' -Force"

echo.
echo ========================================
echo Package created successfully!
echo ========================================
echo.
echo Output: %PACKAGE_NAME%.zip
echo.
echo Contents:
echo   - image-gen-test.exe  ^(CLI tool^)
echo   - igt-tui.exe         ^(TUI interface^)
echo   - README.md
echo   - .env.example
echo   - docs\
echo   - QUICKSTART.txt
echo.

pause
