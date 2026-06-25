@echo off
setlocal EnableExtensions
cd /d %~dp0

set OUT=dictate_native.dll
set INC=native\include
set SRC=native\src\dictate_native.cpp native\src\hotkey_win.cpp native\src\paste_win.cpp native\src\audio_win.cpp

set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
set VSPATH=
set HAS_VCTOOLS=0
set HAS_VS=0

if exist "%VSWHERE%" (
  for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -property installationPath 2^>nul`) do (
    set "VSPATH=%%i"
    set HAS_VS=1
  )
  for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2^>nul`) do set HAS_VCTOOLS=1
)

if "%HAS_VCTOOLS%"=="1" if defined VSPATH goto :msvc_build

REM MinGW g++ (e.g. MSYS2: C:\msys64\mingw64\bin)
if exist "C:\msys64\mingw64\bin\g++.exe" (
  set "PATH=C:\msys64\mingw64\bin;%PATH%"
)
where g++ >nul 2>&1
if %ERRORLEVEL%==0 goto :mingw_build

if "%HAS_VS%"=="1" goto :vs_without_cpp
where cmake >nul 2>&1
if %ERRORLEVEL%==0 goto :cmake_without_msvc
goto :no_toolchain

:msvc_build
echo Using Visual Studio C++ tools...
call "%VSPATH%\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if errorlevel 1 goto :vs_without_cpp
where cl >nul 2>&1
if errorlevel 1 goto :vs_without_cpp

cl /nologo /LD /EHsc /O2 /std:c++17 /I "%INC%" /DUNICODE /D_UNICODE /DDICTATE_NATIVE_EXPORTS ^
  %SRC% /Fe:%OUT% /link user32.lib ole32.lib winmm.lib
if errorlevel 1 goto :msvc_failed

echo Built %OUT% with MSVC.
del *.obj *.exp *.lib >nul 2>&1
exit /b 0

:mingw_build
echo Using MinGW g++...
g++ -shared -O2 -std=c++17 -I "%INC%" -DUNICODE -D_UNICODE -DDICTATE_NATIVE_EXPORTS ^
  %SRC% -o %OUT% -luser32 -lole32 -lwinmm -static-libgcc -static-libstdc++
if errorlevel 1 goto :no_toolchain
echo Built %OUT% with MinGW.
exit /b 0

:msvc_failed
where cmake >nul 2>&1
if %ERRORLEVEL%==0 goto :cmake_build
goto :no_toolchain

:cmake_build
echo Using CMake with Visual Studio generator...
if exist native\build\CMakeCache.txt (
  findstr /C:"CMAKE_GENERATOR:INTERNAL=NMake" native\build\CMakeCache.txt >nul 2>&1
  if not errorlevel 1 (
    echo Removing stale CMake cache - was configured without MSVC.
    rmdir /s /q native\build
  )
)
if not exist native\build mkdir native\build
pushd native\build

cmake .. -G "Visual Studio 17 2022" -A x64
if errorlevel 1 cmake .. -G "Visual Studio 16 2019" -A x64
if errorlevel 1 (
  popd
  goto :vs_without_cpp
)

cmake --build . --config Release
if errorlevel 1 (
  popd
  exit /b 1
)
popd

if exist native\build\bin\dictate_native.dll (
  copy /Y native\build\bin\dictate_native.dll %OUT% >nul
  goto :cmake_done
)
if exist native\build\Release\dictate_native.dll (
  copy /Y native\build\Release\dictate_native.dll %OUT% >nul
  goto :cmake_done
)
if exist native\build\bin\Release\dictate_native.dll (
  copy /Y native\build\bin\Release\dictate_native.dll %OUT% >nul
  goto :cmake_done
)
echo CMake build finished but DLL not found.
exit /b 1

:cmake_done
echo Built %OUT% with CMake.
exit /b 0

:vs_without_cpp
echo.
echo Visual Studio Build Tools is installed, but the C++ compiler is missing.
echo The base package alone does not include MSVC — you need one more workload.
echo.
echo Quick fix — run this script (admin not required):
echo   .\install_cpp_workload.bat
echo.
echo Or manually:
echo   1. Open "Visual Studio Installer" from the Start menu
echo   2. Click Modify on Build Tools 2022
echo   3. Check "Desktop development with C++"
echo   4. Click Modify and wait for it to finish
echo.
echo Then close PowerShell, reopen it, and run:
echo   .\build_native.bat
echo.
exit /b 1

:cmake_without_msvc
echo.
echo CMake is installed, but no C++ compiler was found.
echo.
goto :install_help

:no_toolchain
echo.
echo Could not build dictate_native.dll — no C++ compiler found.
echo.

:install_help
echo Option A — add C++ to your existing Build Tools install:
echo   .\install_cpp_workload.bat
echo.
echo Option B — run without the DLL (Python fallbacks still work):
echo   python main.py
echo.
exit /b 1
