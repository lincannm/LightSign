@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
title LightSign - 一键打包项目

echo.
echo ============================================================
echo   LightSign 轻签 - 一键打包项目
echo ============================================================
echo   按当前 .gitignore 规则打包工作目录，包含未提交的新文件。
echo   自动排除 Git 仓库目录和打包输出目录。
echo.

if /i "%~1"=="--help" goto usage
if /i "%~1"=="-h" goto usage
if not "%~2"=="" goto usage_error

if not exist "%~dp0scripts\package.ps1" (
    echo [错误] 缺少 scripts\package.ps1，请先完整解压或下载项目。
    set "EXIT_CODE=1"
    goto finish
)

rem Pass the optional path as data rather than PowerShell command text.
set "LIGHTSIGN_PACKAGE_OUTPUT=%~1"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\package.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
goto finish

:usage_error
echo [错误] 最多接受一个参数：输出 ZIP 文件路径。
set "EXIT_CODE=1"
goto show_usage

:usage
set "EXIT_CODE=0"
:show_usage
echo 使用方法：双击 package.bat，或在命令行指定输出文件路径。
echo.
echo   package.bat
echo   package.bat "D:\分享目录\LightSign.zip"
echo.
echo 默认输出：项目目录下的 dist\LightSign_时间戳.zip
echo 打包电脑需要安装 Git；接收者只需解压后双击 START.bat。
echo 已存在的 ZIP 不会被覆盖，请换一个文件名。

:finish
echo.
echo 按任意键关闭本窗口...
pause >nul
endlocal & exit /b %EXIT_CODE%
