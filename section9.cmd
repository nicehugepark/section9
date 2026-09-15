@echo off
rem section9 -- double-click start (REQ-20260915-006-62x6).  ASCII only: cmd.exe
rem reads .cmd in the console code page.  Moves to its own folder and runs
rem `bin\s9.cmd code` in this window (first run: repo, install, login guidance,
rem then Claude Code).  On failure the window stays open until a key is pressed.
setlocal
title section9
cd /d "%~dp0"
call "%~dp0bin\s9.cmd" code %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo section9 ended with exit code %RC% -- read the lines above, then press a key.  1>&2
  pause
)
endlocal & exit /b %RC%
