@echo off
setlocal
rem Always run from the project root, even when double-clicked from installer\
cd /d "%~dp0.."
echo Project: %CD%

rem --- Python ---
set "PY=python"
where python >nul 2>nul || set "PY=py"
%PY% --version || (echo Python not found. Install Python and tick "Add to PATH". & goto :fail)

rem --- build the exe ---
%PY% -m pip install -r requirements-build.txt || goto :fail
%PY% -m pip install -U yt-dlp imageio-ffmpeg pystray || goto :fail
%PY% build.py || goto :fail
if not exist "dist\OpenDM-windows.exe" (echo dist\OpenDM-windows.exe was not created. & goto :fail)
if not exist "ffmpeg\ffmpeg.exe" echo WARNING: ffmpeg\ffmpeg.exe not found - installer will not bundle ffmpeg.

rem --- find Inno Setup compiler ---
set "ISCC="
for %%P in (
  "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
  "%ProgramFiles%\Inno Setup 7\ISCC.exe"
  "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
) do if exist %%P if not defined ISCC set "ISCC=%%~P"
if not defined ISCC (echo Inno Setup compiler ISCC.exe not found. Edit this file and set ISCC. & goto :fail)
echo Using: %ISCC%

"%ISCC%" "installer\OpenDM.iss" || goto :fail
echo.
echo DONE: dist\OpenDM-Setup-1.6.0.exe
pause
exit /b 0

:fail
echo.
echo BUILD FAILED - see the messages above.
pause
exit /b 1
