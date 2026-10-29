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

function Invoke-NativeVisible {
    # Run a console program, print its output as plain lines and return only its
    # exit code. ErrorRecords from stderr are printed as text instead of the
    # noisy "NativeCommandError" block, so progress output stays readable.
    param([string]$FilePath, [string[]]$Arguments)

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $FilePath @Arguments 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) { Write-Host $_.Exception.Message }
            else { Write-Host ([string]$_) }
        }
        return $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previous }
}

function Invoke-NativeQuiet {
    param([string]$FilePath, [string[]]$Arguments)

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $FilePath @Arguments 2>$null | Out-Null
        return $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previous }
}

function Find-Uv {
    $command = Get-Command uv.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    $candidates = @(
        $(if ($command) { $command.Source }),
        (Join-Path $env:LOCALAPPDATA 'LightSign\bin\uv.exe'),
        (Join-Path $env:USERPROFILE '.local\bin\uv.exe')
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            if ((Invoke-NativeVisible $candidate @('--version')) -eq 0) { return $candidate }
        }
    }
    return $null
}

function Get-PythonMajorMinor {
    param([string]$PythonPath)

    if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { return $null }
    try {
        $output = & $PythonPath -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $output) { return ([string]$output).Trim() }
    }
    catch { }
    return $null
}

function Test-ProjectImports {
    param([string]$PythonPath)

    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { return $false }
    try {
        & $PythonPath -c "import streamlit, cv2, numpy, pandas" 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    }
    catch { return $false }
}

function Find-NativePython312 {
    $candidates = New-Object 'System.Collections.Generic.List[string]'

    $launcher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($launcher) {
        try {
            $output = & $launcher.Source -3.12 -c "import sys;print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $output) { $candidates.Add(([string]$output).Trim()) }
        }
        catch { }
    }
    foreach ($name in @('python.exe', 'python3.12.exe')) {
        $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) { $candidates.Add($command.Source) }
    }
    if ($env:LOCALAPPDATA) { $candidates.Add((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe')) }
    if ($env:ProgramFiles) { $candidates.Add((Join-Path $env:ProgramFiles 'Python312\python.exe')) }
    if (${env:ProgramFiles(x86)}) { $candidates.Add((Join-Path ${env:ProgramFiles(x86)} 'Python312\python.exe')) }
    $candidates.Add('C:\Python312\python.exe')

    foreach ($candidate in $candidates) {
        if ((Get-PythonMajorMinor $candidate) -eq '3.12') { return $candidate }
    }
    return $null
}

function Get-SystemPythonVersion {
    $command = Get-Command 'python.exe' -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) {
        $version = Get-PythonMajorMinor $command.Source
        if ($version) { return $version }
    }
    $launcher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($launcher) {
        try {
            $output = & $launcher.Source -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and $output) { return ([string]$output).Trim() }
        }
        catch { }
    }
    return $null
}

function Invoke-NativeSetup {
    # Build .venv with the user's own Python 3.12 and install dependencies with pip.
    param([string]$PythonPath)

    $venvDir = Join-Path $root '.venv'
    $venvPython = Join-Path $venvDir 'Scripts\python.exe'
    Write-Host ("[2/3] 使用本机 Python 创建项目虚拟环境：{0}" -f $PythonPath)
    Invoke-NativeQuiet $PythonPath @('-m', 'venv', '--clear', $venvDir) | Out-Null
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        Write-Host '  创建虚拟环境失败，没有生成 .venv\Scripts\python.exe。' -ForegroundColor Yellow
        return $false
    }

    if ((Invoke-NativeQuiet $venvPython @('-m', 'pip', '--version')) -ne 0) {
        Write-Host '  虚拟环境缺少 pip，正在尝试初始化...' -ForegroundColor Yellow
        Invoke-NativeQuiet $venvPython @('-m', 'ensurepip', '--upgrade') | Out-Null
    }
    if ((Invoke-NativeQuiet $venvPython @('-m', 'pip', '--version')) -ne 0) {
        Write-Host '  本机的 Python 3.12 缺少 pip 与 ensurepip，无法用它安装依赖。' -ForegroundColor Yellow
        return $false
    }

    $mirror = 'https://pypi.tuna.tsinghua.edu.cn/simple'
    Write-Host '  正在安装项目依赖，首次需要下载较多文件，请耐心等待...'
    Invoke-NativeQuiet $venvPython @('-m', 'pip', 'install', '--disable-pip-version-check', '--quiet', '--upgrade', 'pip', '-i', $mirror) | Out-Null
    $installCode = Invoke-NativeVisible $venvPython @('-m', 'pip', 'install', '--disable-pip-version-check', '-e', $root, '-i', $mirror)
    if ($installCode -ne 0) {
        Write-Host '  镜像源安装失败，改用官方 PyPI 重试...' -ForegroundColor Yellow
        $installCode = Invoke-NativeVisible $venvPython @('-m', 'pip', 'install', '--disable-pip-version-check', '-e', $root)
    }
    if ($installCode -ne 0) {
        Write-Host '  依赖安装失败。' -ForegroundColor Yellow
        return $false
    }
    if (-not (Test-ProjectImports $venvPython)) {
        Write-Host '  依赖已安装，但导入检查未通过。' -ForegroundColor Yellow
        return $false
    }
    Write-Host '  依赖安装完成。'
    return $true
}

function Read-EnvironmentChoice {
    param(
        [string]$DetectedVersion,
        [switch]$SetupFailed
    )

    Write-Host ''
    if ($SetupFailed) {
        Write-Host '[提示] 没有找到 uv，也没能用本机的 Python 3.12 自动装好依赖。' -ForegroundColor Yellow
        if ($DetectedVersion) {
            Write-Host ("  检测到的本机 Python 版本：{0}，本项目需要 3.12，并且需要该 Python 自带 pip。" -f $DetectedVersion)
        }
    }
    else {
        Write-Host '[提示] 没有找到 uv，本机也没有可用的 Python 3.12。' -ForegroundColor Yellow
        if ($DetectedVersion) {
            Write-Host ("  检测到本机 Python 版本为 {0}，本项目需要 Python 3.12。" -f $DetectedVersion)
        }
    }
    Write-Host '  请选择下一步（输入数字后按回车）：'
    Write-Host '    1) 自动安装 uv（官方安装脚本，需要联网；只装到当前用户目录，不改动系统 Python）'
    if ($SetupFailed) {
        Write-Host '    2) 我自己修复或重装带 pip 的 Python 3.12，装好后再重新运行 START.bat'
    }
    else {
        Write-Host '    2) 我自己安装 Python 3.12，装好后再重新运行 START.bat'
    }
    Write-Host '    3) 退出'
    while ($true) {
        try { $answer = Read-Host '请输入 1、2 或 3' }
        catch { return 'cancel' }
        if ($null -eq $answer) { return 'cancel' }
        switch ($answer.Trim()) {
            '1' { return 'uv' }
            '2' { return 'python' }
            '3' { return 'cancel' }
        }
        Write-Host '  输入无效，请重新输入 1、2 或 3。' -ForegroundColor Yellow
    }
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

    Write-Host '[1/3] 检查项目文件和本机 Python 环境...'
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

    $venvPython = Join-Path $root '.venv\Scripts\python.exe'
    $environmentReady = $false
    $uv = Find-Uv

    if ($uv) {
        Write-Host ("  使用 uv 管理环境：{0}" -f $uv)
        Write-Host ''
        Write-Host '[2/3] 准备 Python 3.12 和项目依赖...'
        Write-Host '首次运行会自动下载 Python 和依赖，耗时取决于网络，请耐心等待。'
        # Keep uv.lock authoritative and preserve installed experiment extras.
        if ((Invoke-NativeVisible $uv @('sync', '--locked', '--python', '3.12', '--inexact')) -ne 0) {
            throw 'Python 或依赖安装失败。请检查上方输出、网络和磁盘空间；若锁文件不一致，请重新下载完整项目。'
        }
        $environmentReady = $true
    }
    else {
        Write-Host '  未找到 uv，优先使用本机已安装的 Python 3.12。'
        if ((Get-PythonMajorMinor $venvPython) -eq '3.12' -and (Test-ProjectImports $venvPython)) {
            Write-Host '[2/3] 项目内已有可用的 Python 3.12 虚拟环境，跳过安装。'
            $environmentReady = $true
        }
        else {
            $nativePython = Find-NativePython312
            if ($nativePython) { $environmentReady = Invoke-NativeSetup $nativePython }
            if (-not $environmentReady) {
                $detectedVersion = Get-SystemPythonVersion
                if ($nativePython) { $choice = Read-EnvironmentChoice $detectedVersion -SetupFailed }
                else { $choice = Read-EnvironmentChoice $detectedVersion }
                if ($choice -eq 'uv') {
                    Write-Host ''
                    Write-Host '  正在从官方来源安装 uv，请保持联网...'
                    $env:UV_INSTALL_DIR = Join-Path $env:LOCALAPPDATA 'LightSign\bin'
                    $env:UV_NO_MODIFY_PATH = '1'
                    Write-Host ("  安装位置：{0}" -f $env:UV_INSTALL_DIR)
                    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
                    try {
                        Invoke-RestMethod -Uri 'https://astral.sh/uv/install.ps1' | Invoke-Expression
                        $uv = Find-Uv
                    }
                    catch {
                        throw "uv 安装失败：$($_.Exception.Message) 请检查网络，或执行 winget install --id astral-sh.uv --exact 后重新运行 START.bat。"
                    }
                    if (-not $uv) { throw 'uv 安装完成后仍未找到可用的 uv，已停止启动。' }
                    Write-Host ''
                    Write-Host '[2/3] 使用 uv 准备 Python 3.12 和项目依赖...'
                    if ((Invoke-NativeVisible $uv @('sync', '--locked', '--python', '3.12', '--inexact')) -ne 0) {
                        throw 'Python 或依赖安装失败。请检查上方输出、网络和磁盘空间。'
                    }
                    $environmentReady = $true
                }
                elseif ($choice -eq 'python') {
                    Write-Host ''
                    Write-Host '请先安装 Python 3.12，装好后再重新运行 START.bat：'
                    Write-Host '  https://www.python.org/downloads/（安装时勾选 Add python.exe to PATH，官方安装包自带 pip）'
                    Write-Host '  或执行：winget install --id Python.Python.3.12 --exact'
                    Write-Host '脚本会自动用本机 Python 3.12 建好 .venv 并安装依赖，无需手动激活环境。'
                    exit 1
                }
                else {
                    Write-Host ''
                    Write-Host '已退出，未对系统做任何改动。'
                    exit 0
                }
            }
        }
    }

    if (-not $environmentReady) { throw '运行环境未就绪，已停止启动。' }

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
    # Launch without piping so the child keeps the real console handles.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $root 'run.py') @LaunchArguments
        $exitCode = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previousPreference }
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
