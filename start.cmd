@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "URL=http://127.0.0.1:8765/Tools/index.html"

echo.
echo  QLU Newsletter Tools
echo  --------------------
echo  Index:   %URL%
echo  Outputs: %~dp0out
echo.
echo  Test from the hub:
echo    1. Download YouTube captions
echo    2. Extract frame at time
echo    3. Telugu speech to text
echo    4. Beautify text / newsletter
echo.
echo  Keep this window open. Ctrl+C stops the server.
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo Python not found on PATH. Install Python 3.10+ and try again.
  pause
  exit /b 1
)

REM Open index after a short delay while the server starts
start "QLU Tools browser" /min cmd /c "ping -n 3 127.0.0.1 >nul & start %URL%"

python serve.py --no-browser --host 127.0.0.1 --port 8765
set "ERR=%ERRORLEVEL%"

if not "%ERR%"=="0" (
  echo.
  echo Server exited with code %ERR%.
  pause
)

endlocal
exit /b %ERR%
