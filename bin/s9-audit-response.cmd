@echo off
rem section9 Windows entry for `s9-audit-response`  --  see docs/11-windows.md (REQ-20260903-005)
rem ASCII only on purpose: cmd.exe reads .cmd in the console code page.
rem Runs the tool exactly once, avoids the Microsoft Store python stub,
rem forces UTF-8 output, and propagates the exit code.
setlocal
set "PYTHONUTF8=1"
set "S9_PY="

py -3 -c "" >nul 2>nul
if not errorlevel 1 set "S9_PY=py"
if defined S9_PY goto :run

python -c "" >nul 2>nul
if not errorlevel 1 set "S9_PY=python"
if defined S9_PY goto :run

for %%R in ("%LOCALAPPDATA%\Programs\Python" "%ProgramFiles%" "%ProgramFiles(x86)%") do (
  if exist "%%~R" for /f "delims=" %%D in ('dir /b /ad /o-n "%%~R\Python3*" 2^>nul') do (
    if exist "%%~R\%%D\python.exe" (
      set "S9_PY=%%~R\%%D\python.exe"
      goto :run
    )
  )
)

echo s9: Python 3 not found. Install it, then run this again.  1>&2
echo     winget install Python.Python.3.12    ^(docs/11-windows.md^)  1>&2
exit /b 127

:run
if "%S9_PY%"=="py" (py -3 "%~dp0s9-audit-response" %*) else ("%S9_PY%" "%~dp0s9-audit-response" %*)
exit /b %ERRORLEVEL%
