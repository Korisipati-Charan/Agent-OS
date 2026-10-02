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

echo [1/3] Verifying build prerequisites...
.\.venv\Scripts\python.exe -m pip install --quiet pyinstaller

echo [2/3] Running PyInstaller build (AgentOS.spec)...
.\.venv\Scripts\python.exe -m PyInstaller --clean AgentOS.spec

if %ERRORLEVEL% neq 0 (
    echo.
    echo [AgentOS Error] Build failed with error code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
)

echo.
echo [3/3] Safe Authenticode Code-Signing verification...
.\.venv\Scripts\python.exe -m agentos.security.code_signing dist\AgentOS.exe

echo.
echo ===================================================
echo   Build Succeeded: dist\AgentOS.exe
echo ===================================================
endlocal
