@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem NOTE: keep every rem line pure ASCII. cmd mis-parses lines that mix
rem Chinese with the rem keyword under chcp 65001 -- it splits the line at
rem a byte boundary and tries to run the tail as a command.
rem Chinese is fine inside echo, which is what the user actually reads.

echo.
echo   正在安装 PDF 工作台，请稍候...
echo.

if not exist "%~dp0install.ps1" goto :incomplete

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
rem pause resets ERRORLEVEL to 0, so save it first or failures look like success
set "RC=%ERRORLEVEL%"

echo.
pause
exit /b %RC%

:incomplete
echo   缺少 install.ps1，这个文件夹是不完整的。
echo.
echo   最常见的原因：直接在压缩包里双击了本文件。
echo   Windows 只会把被双击的那一个文件解压出来，其余都还在压缩包里。
echo.
echo   正确做法：右键 zip 文件 - 全部解压 - 进入解压出的文件夹 - 再双击 安装.bat
echo.
pause
exit /b 1
