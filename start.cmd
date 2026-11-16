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
echo    2. Extract frame at time  ^(needs ffmpeg via requirements.txt^)
echo    3. Voice type / Whisper  ^(Telugu default; glossary-aware^)
echo    4. Beautify text / Publication prompts
echo.
echo  Keep this window open. Ctrl+C stops the server.
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo  ERROR: Python not found on PATH.
  echo.
  echo  Install Python 3.10+ from:
  echo    https://www.python.org/downloads/
  echo  Check "Add python.exe to PATH", then re-open this window.
  echo.
  pause
  exit /b 1
)

python "%~dp0scripts\check_python_env.py"
if errorlevel 1 (
  echo.
  echo  Download: https://www.python.org/downloads/
  echo  During setup, check "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)

echo Checking Python packages ^(yt-dlp, imageio-ffmpeg, whisper^)...
python -m pip install -r "%~dp0requirements.txt" -q
if errorlevel 1 (
  echo.
  echo  ERROR: pip install failed.
  echo.
  echo  Try manually:
  echo    python -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

python -c "from imageio_ffmpeg import get_ffmpeg_exe; p=get_ffmpeg_exe(); print('  ffmpeg OK:', p)" 2>nul
if errorlevel 1 (
  echo.
  echo WARNING: bundled ffmpeg not available.
  echo   python -m pip install -r requirements.txt
  echo   or: winget install Gyan.FFmpeg
  echo Captions still work; Extract frame will fail until ffmpeg is fixed.
  echo.
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
