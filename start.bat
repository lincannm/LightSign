@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
title LightSign - 轻签一键部署与启动

rem Always use the script directory, including when launched from another drive.
pushd "%~dp0"
if errorlevel 1 goto directory_error

set "PYTHONIOENCODING=utf-8"
set "UV_PROJECT_ENVIRONMENT=%CD%\.venv"
set "EXIT_CODE=0"

echo.
echo ============================================================
echo   LightSign 轻签 - 一键部署与启动
echo ============================================================
echo   首次使用需要联网，请保持本窗口打开。
echo   已部署过的电脑会复用本地环境，无需手动激活。
echo.

if /i "%~1"=="--help" goto usage
if /i "%~1"=="-h" goto usage

echo [1/3] 检查项目文件和 uv 环境管理工具...
for %%F in (run.py app.py participant.py pyproject.toml uv.lock light_sign\store.py models\policy.json models\haarcascade_frontalface_default.xml results\vision_summary.json results\system_checks.json) do (
    if not exist "%%F" (
        echo [错误] 缺少文件：%%F
        echo 请先完整解压或下载项目，再双击 start.bat。
        goto failed
    )
)

call :find_uv
if defined UV_EXE goto prepare_environment

echo 未找到 uv，正在从官方来源安装到当前用户目录...
echo 安装位置："%LOCALAPPDATA%\LightSign\bin"
set "UV_INSTALL_DIR=%LOCALAPPDATA%\LightSign\bin"
set "UV_NO_MODIFY_PATH=1"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { Invoke-RestMethod -Uri 'https://astral.sh/uv/install.ps1' | Invoke-Expression } catch { Write-Error $_; exit 1 }"
if errorlevel 1 goto install_error
call :find_uv
if not defined UV_EXE goto install_error

:prepare_environment
echo.
echo [2/3] 准备 Python 3.12 和项目依赖...
echo 首次运行会自动下载 Python 和依赖，耗时取决于网络，请耐心等待。
rem Keep uv.lock authoritative and preserve any installed experiment extras.
"%UV_EXE%" sync --locked --python 3.12 --inexact
if errorlevel 1 goto sync_error

echo.
echo [3/3] 环境已就绪，正在启动组织者和参与者服务...
echo 出现入口地址后，在浏览器中打开组织者入口即可使用。
echo 默认组织者入口：https://localhost:8503/
echo 首次访问自签名 HTTPS 页面会有安全提示，请核对地址后继续访问。
echo 手机请连接同一 Wi-Fi；防火墙如有提示，请允许 Python 访问专用网络。
echo 使用期间保持本窗口打开，按 Ctrl+C 可停止两个服务。
echo.
rem Use the environment's interpreter directly; run.py owns child-process cleanup.
".venv\Scripts\python.exe" run.py %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" goto run_error
echo.
echo 服务已停止。下次使用时再次双击 start.bat 即可。
goto finish

:find_uv
set "UV_EXE="
for %%U in (uv.exe) do set "UV_EXE=%%~$PATH:U"
if defined UV_EXE goto check_uv
if exist "%LOCALAPPDATA%\LightSign\bin\uv.exe" set "UV_EXE=%LOCALAPPDATA%\LightSign\bin\uv.exe"
if defined UV_EXE goto check_uv
if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV_EXE=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV_EXE exit /b 0
:check_uv
"%UV_EXE%" --version
if errorlevel 1 set "UV_EXE="
exit /b 0

:usage
echo 使用方法：双击 start.bat，或在命令行执行 start.bat [启动参数]
echo.
echo 常用示例：
echo   start.bat                                 默认 HTTPS 双端启动
echo   start.bat --http                          使用 HTTP 模式
echo   start.bat --organizer-port 9003 --participant-port 9004
echo.
echo 其他参数与 run.py 一致，自定义端口或 HTTP 模式请以实际输出地址为准。
goto finish

:install_error
echo.
echo [错误] uv 安装失败。请检查网络，以及是否能访问 astral.sh 和 GitHub。
echo 也可以先在 PowerShell 中执行以下命令，安装后再次双击本脚本：
echo   winget install --id astral-sh.uv --exact
goto failed

:sync_error
echo.
echo [错误] Python 或依赖安装失败，详细原因见上方输出。
echo 请检查网络和剩余磁盘空间，恢复后再次双击即可重试。
echo 若提示 uv.lock 与 pyproject.toml 不一致，请重新下载完整项目。
goto failed

:run_error
echo.
echo [错误] 服务启动失败或异常退出，退出码：%EXIT_CODE%
echo 请查看上方错误；若端口被占用，请先关闭之前的启动窗口。
echo 也可以在命令行执行以下命令，改用其他端口：
echo   start.bat --organizer-port 9003 --participant-port 9004
goto finish

:failed
set "EXIT_CODE=1"

:finish
echo.
echo 按任意键关闭本窗口...
pause >nul
popd
endlocal & exit /b %EXIT_CODE%

:directory_error
echo [错误] 无法进入项目目录，请将项目解压到有读写权限的文件夹。
pause
endlocal & exit /b 1
