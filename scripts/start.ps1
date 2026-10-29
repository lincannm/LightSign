#requires -Version 5.1
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$LaunchArguments
)

$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$exitCode = 1
$locationPushed = $false

function Find-Uv {
    $command = Get-Command uv.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    $candidates = @(
        $(if ($command) { $command.Source }),
        (Join-Path $env:LOCALAPPDATA 'LightSign\bin\uv.exe'),
        (Join-Path $env:USERPROFILE '.local\bin\uv.exe')
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            & $candidate --version | Out-Host
            if ($LASTEXITCODE -eq 0) { return $candidate }
        }
    }
    return $null
}

try {
    Push-Location -LiteralPath $root
    $locationPushed = $true
    $env:PYTHONIOENCODING = 'utf-8'
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $root '.venv'

    Write-Host ''
    Write-Host '============================================================'
    Write-Host '  LightSign 轻签 - 一键部署与启动'
    Write-Host '============================================================'
    Write-Host '  首次使用需要联网，请保持本窗口打开。'
    Write-Host '  已部署过的电脑会复用本地环境，无需手动激活。'
    Write-Host ''

    if ($LaunchArguments.Count -gt 0 -and $LaunchArguments[0] -in @('--help', '-h')) {
        Write-Host '使用方法：双击 START.bat，或在命令行执行 START.bat [启动参数]'
        Write-Host ''
        Write-Host '常用示例：'
        Write-Host '  START.bat                                 默认 HTTPS 双端启动'
        Write-Host '  START.bat --http                          使用 HTTP 模式'
        Write-Host '  START.bat --organizer-port 9003 --participant-port 9004'
        Write-Host ''
        Write-Host '其他参数与 run.py 一致，自定义端口或 HTTP 模式请以实际输出地址为准。'
        exit 0
    }

    Write-Host '[1/3] 检查项目文件和 uv 环境管理工具...'
    $requiredFiles = @(
        'run.py', 'app.py', 'participant.py', 'pyproject.toml', 'uv.lock',
        'light_sign\store.py', 'light_sign\vision.py',
        'models\yunet_policy.json', 'models\yunet.provenance.json',
        'models\face_detection_yunet_2023mar.onnx', 'models\LICENSE.yunet'
    )
    foreach ($name in $requiredFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $root $name) -PathType Leaf)) {
            throw "缺少文件：$name。请先完整解压或下载项目，再双击 START.bat。"
        }
    }

    $uv = Find-Uv
    if (-not $uv) {
        Write-Host '未找到 uv，正在从官方来源安装到当前用户目录...'
        $env:UV_INSTALL_DIR = Join-Path $env:LOCALAPPDATA 'LightSign\bin'
        $env:UV_NO_MODIFY_PATH = '1'
        Write-Host ("安装位置：{0}" -f $env:UV_INSTALL_DIR)
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        try {
            Invoke-RestMethod -Uri 'https://astral.sh/uv/install.ps1' | Invoke-Expression
            $uv = Find-Uv
            if (-not $uv) { throw '安装后仍未找到可用的 uv。' }
        }
        catch {
            throw "uv 安装失败：$($_.Exception.Message) 请检查网络，或执行 winget install --id astral-sh.uv --exact 后重试。"
        }
    }

    Write-Host ''
    Write-Host '[2/3] 准备 Python 3.12 和项目依赖...'
    Write-Host '首次运行会自动下载 Python 和依赖，耗时取决于网络，请耐心等待。'
    # Keep uv.lock authoritative and preserve installed experiment extras.
    & $uv sync --locked --python 3.12 --inexact
    if ($LASTEXITCODE -ne 0) {
        throw 'Python 或依赖安装失败。请检查上方输出、网络和磁盘空间；若锁文件不一致，请重新下载完整项目。'
    }

    Write-Host ''
    Write-Host '[3/3] 环境已就绪，正在启动组织者和参与者服务...'
    Write-Host '出现入口地址后，在浏览器中打开组织者入口即可使用。'
    Write-Host '组织者入口默认同时提供两种地址：'
    Write-Host '  本机    https://localhost:8503/'
    Write-Host '  局域网  启动后显示，与签到入口使用同一个 IP。'
    Write-Host '首次访问自签名 HTTPS 页面会有安全提示，请核对地址后继续访问。'
    Write-Host '手机请连接同一 Wi-Fi；防火墙如有提示，请允许 Python 访问专用网络。'
    Write-Host '使用期间保持本窗口打开，按 Ctrl+C 可停止两个服务。'
    Write-Host ''
    # Splat arguments as data; never evaluate user-supplied command text.
    & (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $root 'run.py') @LaunchArguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-Host ("[错误] 服务启动失败或异常退出，退出码：{0}" -f $exitCode) -ForegroundColor Red
        Write-Host '请查看上方错误；若端口被占用，请先关闭之前的启动窗口。'
        Write-Host '也可以执行 START.bat --organizer-port 9003 --participant-port 9004。'
    }
    else {
        Write-Host '服务已停止。下次使用时再次双击 START.bat 即可。'
    }
}
catch {
    Write-Host ("[错误] {0}" -f $_.Exception.Message) -ForegroundColor Red
    $exitCode = 1
}
finally {
    if ($locationPushed) { Pop-Location }
    Write-Host ''
    Write-Host '按任意键关闭本窗口...'
}
exit $exitCode
