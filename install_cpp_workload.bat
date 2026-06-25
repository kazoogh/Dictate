@echo off
setlocal EnableExtensions

REM Passive/quiet VS installer modify requires elevation.
net session >nul 2>&1
if errorlevel 1 (
  echo Administrator access is required to install the C++ compiler.
  echo Approve the UAC prompt, then wait for the installer to finish.
  echo.
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs -Wait"
  exit /b %errorlevel%
)

set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
set "INSTALLER=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\setup.exe"

if not exist "%VSWHERE%" (
  echo Visual Studio Installer not found.
  exit /b 1
)

set VSPATH=
for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -property installationPath 2^>nul`) do set "VSPATH=%%i"

if not defined VSPATH (
  echo No Visual Studio installation found.
  echo Run: winget install Microsoft.VisualStudio.2022.BuildTools
  exit /b 1
)

for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -property displayName 2^>nul`) do set "VSDISPLAY=%%i"

echo Found: %VSDISPLAY%
echo Path:  %VSPATH%
echo.
echo Installing "Desktop development with C++" workload...
echo This may take several minutes.
echo.

"%INSTALLER%" modify ^
  --installPath "%VSPATH%" ^
  --add Microsoft.VisualStudio.Workload.VCTools ^
  --includeRecommended ^
  --passive ^
  --norestart

set ERR=%errorlevel%
if not "%ERR%"=="0" (
  echo.
  echo Automatic install failed (exit code %ERR%^).
  echo Opening the installer so you can add the workload manually...
  start "" "%INSTALLER%"
  echo.
  echo   1. Click Modify on Build Tools 2022
  echo   2. Check "Desktop development with C++"
  echo   3. Click Modify and wait for it to finish
  exit /b 1
)

echo.
echo C++ workload installed. Close and reopen PowerShell, then run:
echo   cd C:\Users\INTERN4\Dictate
echo   .\build_native.bat
exit /b 0
