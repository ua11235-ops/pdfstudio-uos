@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem NOTE: keep every rem line pure ASCII -- see the install script for why.

if not exist "%~dp0uninstall.ps1" goto :incomplete

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
rem pause resets ERRORLEVEL to 0, so save it first
set "RC=%ERRORLEVEL%"

echo.
pause
exit /b %RC%

:incomplete
echo.
echo   缺少 uninstall.ps1，这个文件夹是不完整的。
echo.
echo   如果程序已经装在电脑上，可以直接删掉这个目录：
echo     %%LOCALAPPDATA%%\Programs\PDFStudio
echo   然后再手动删掉桌面和开始菜单里的「PDF 工作台」快捷方式。
echo.
pause
exit /b 1
