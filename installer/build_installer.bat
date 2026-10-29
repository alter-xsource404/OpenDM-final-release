@echo off
setlocal
rem Always run from the project root, even when double-clicked from installer\
cd /d "%~dp0.."
echo Project: %CD%

set "PY=python"
where python >nul 2>nul || set "PY=py"
%PY% --version || (echo Python not found. Install Python and tick "Add to PATH". & goto :fail)

%PY% -m pip install -r requirements-build.txt || goto :fail
%PY% -m pip install -U yt-dlp pystray || goto :fail

if not exist "ffmpeg\ffmpeg.exe" echo WARNING: ffmpeg\ffmpeg.exe not found - video+audio merging will not work in the built files.

rem --- 1) single-file exe: dist\OpenDM-windows.exe (ffmpeg embedded when ffmpeg\ffmpeg.exe exists) ---
%PY% build.py --portable --bundle-ffmpeg || goto :fail
if not exist "dist\OpenDM-windows.exe" (echo dist\OpenDM-windows.exe was not created. & goto :fail)

rem --- 2) program folder: dist\OpenDM\OpenDM.exe (+ ffmpeg.exe) - this is what the installer packs ---
%PY% build.py || goto :fail
if not exist "dist\OpenDM\OpenDM.exe" (echo dist\OpenDM\OpenDM.exe was not created. & goto :fail)

rem --- 3) installer (optional: skipped when Inno Setup is not installed) ---
set "ISCC="
for %%P in (
  "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
  "%ProgramFiles%\Inno Setup 7\ISCC.exe"
  "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
) do if exist %%P if not defined ISCC set "ISCC=%%~P"
if not defined ISCC (
  echo.
  echo Inno Setup not found - installer skipped. The exe files above are ready.
  goto :done
)
echo Using: %ISCC%
"%ISCC%" "installer\OpenDM.iss" || goto :fail

:done
echo.
echo DONE. Output in dist\ :
dir /b dist
pause
exit /b 0

:fail
echo.
echo BUILD FAILED - see the messages above.
pause
exit /b 1
