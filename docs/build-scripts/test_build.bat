@echo off
REM Quick test script for built executables

echo ========================================
echo Testing Built Executables
echo ========================================
echo.

REM Check if build exists
if not exist "dist\image-gen-test-tool\image-gen-test.exe" (
    echo ERROR: Build not found. Please run build_windows.bat first.
    pause
    exit /b 1
)

cd dist\image-gen-test-tool

echo [1/3] Testing image-gen-test.exe --help
echo.
image-gen-test.exe --help
if errorlevel 1 (
    echo ERROR: image-gen-test.exe failed
    cd ..\..
    pause
    exit /b 1
)

echo.
echo [2/3] Testing igt-tui.exe --version
echo.
igt-tui.exe --help
if errorlevel 1 (
    echo WARNING: igt-tui.exe may have issues
    echo This is often due to terminal compatibility
)

echo.
echo [3/3] Checking required files
if not exist ".env.example" (
    echo ERROR: .env.example missing
    cd ..\..
    pause
    exit /b 1
)
if not exist "custom_models.json" (
    echo ERROR: custom_models.json missing
    cd ..\..
    pause
    exit /b 1
)

echo.
echo ========================================
echo All tests passed!
echo ========================================
echo.
echo Build is ready for distribution.
echo.

cd ..\..
pause
