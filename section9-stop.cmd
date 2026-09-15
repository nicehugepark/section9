@echo off
rem section9 -- stop the dashboard server (REQ-20260915-006-62x6).  ASCII only.
rem Runs `bin\s9.cmd serve --stop`: the watcher is stopped first, then the server
rem (stopping the server alone lets the watcher bring it back).  Documents and
rem settings are untouched; the next start puts everything back.  On failure the
rem window stays open until a key is pressed.
setlocal
title section9 stop
cd /d "%~dp0"
call "%~dp0bin\s9.cmd" serve --stop %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo section9 stop ended with exit code %RC% -- read the lines above, then press a key.  1>&2
  pause
)
endlocal & exit /b %RC%
