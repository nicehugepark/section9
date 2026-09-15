@echo off
rem section9 -- dashboard only (REQ-20260915-006-62x6).  ASCII only.
rem Runs `bin\s9.cmd code --no-claude`: starts the dashboard server if it is not
rem running and opens the browser, then this window closes by itself.  On failure
rem the window stays open until a key is pressed.
setlocal
title section9 dashboard
cd /d "%~dp0"
call "%~dp0bin\s9.cmd" code --no-claude %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo section9 dashboard ended with exit code %RC% -- read the lines above, then press a key.  1>&2
  pause
)
endlocal & exit /b %RC%
