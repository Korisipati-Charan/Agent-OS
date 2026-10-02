@echo off
setlocal
echo ===================================================
echo   Building Standalone AgentOS Windows Executable
echo ===================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [AgentOS Error] Python virtual environment not found in .venv.
    pause
    exit /b 1
)

echo [1/2] Verifying build prerequisites...
.\.venv\Scripts\python.exe -m pip install --quiet pyinstaller

echo [2/2] Running PyInstaller build (AgentOS.spec)...
.\.venv\Scripts\python.exe -m PyInstaller --clean AgentOS.spec

if %ERRORLEVEL% equ 0 (
    echo.
    echo ===================================================
    echo   Build Succeeded: dist\AgentOS.exe
    echo ===================================================
) else (
    echo.
    echo [AgentOS Error] Build failed with error code %ERRORLEVEL%.
)
endlocal
