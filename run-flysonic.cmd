@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run_flysonic.py %*
    goto finished
)
py -3.11 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 (
    py -3.11 run_flysonic.py %*
    goto finished
)
python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 (
    python run_flysonic.py %*
    goto finished
)
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 (
    py -3 run_flysonic.py %*
    goto finished
)
echo [flysonic] No se encontro Python 3.11 o posterior.
echo Instala Python desde https://www.python.org/downloads/windows/
pause
exit /b 1
:finished
set "flysonic_exit=%errorlevel%"
if not "%flysonic_exit%"=="0" (
    echo [flysonic] El inicio fallo. Revisa el mensaje anterior.
    pause
)
exit /b %flysonic_exit%
