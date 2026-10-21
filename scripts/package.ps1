#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$OutputPath = $env:LIGHTSIGN_PACKAGE_OUTPUT
)

$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$createdArchive = $false
$archivePath = $null
$archive = $null
$archiveStream = $null

function Invoke-GitText {
    param([string]$GitArguments)

    # Preserve NUL delimiters and UTF-8 names instead of parsing console lines.
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $script:gitPath
    $info.Arguments = $GitArguments
    $info.WorkingDirectory = $script:root
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $info.StandardErrorEncoding = New-Object System.Text.UTF8Encoding($false)
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $info
    try {
        if (-not $process.Start()) { throw '无法运行 Git。' }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $outputText = $stdout.GetAwaiter().GetResult()
        $errorText = $stderr.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) {
            throw "Git 命令执行失败：$errorText"
        }
        return $outputText
    }
    finally { $process.Dispose() }
}

try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $git = Get-Command git.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $git) {
        throw '未找到 Git，请先安装 Git for Windows 并重新打开脚本。打包无需安装 Python。'
    }
    $gitPath = $git.Source
    if (-not (Test-Path -LiteralPath (Join-Path $root '.git'))) {
        throw '打包需要原始 Git 工作目录。请在克隆的项目中运行 package.bat；收到 ZIP 的使用者可直接运行 START.bat。'
    }
    $gitRoot = (Invoke-GitText 'rev-parse --show-toplevel').TrimEnd([char[]]@(13, 10))
    if (-not [string]::Equals([System.IO.Path]::GetFullPath($gitRoot), $root, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Git 仓库根目录与项目目录不一致，已停止打包。'
    }

    if ([string]::IsNullOrWhiteSpace($OutputPath)) {
        $OutputPath = 'dist\LightSign_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff') + '.zip'
    }
    if (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
        $OutputPath = Join-Path $root $OutputPath
    }
    $archivePath = [System.IO.Path]::GetFullPath($OutputPath)
    if ([System.IO.Path]::GetExtension($archivePath) -ine '.zip') {
        throw '输出文件必须以 .zip 结尾。'
    }
    if (Test-Path -LiteralPath $archivePath) {
        throw "输出文件已存在，未覆盖：$archivePath。请换一个文件名。"
    }
    Write-Host '[1/3] 按 .gitignore 筛选项目文件...'

    # Only repository .gitignore files control the package, not personal global rules.
    $splitOptions = [System.StringSplitOptions]::RemoveEmptyEntries
    $candidates = (Invoke-GitText 'ls-files --cached --others --exclude-per-directory=.gitignore -z').Split([char]0, $splitOptions)
    # --cached alone includes tracked files even when they are now ignored.
    $ignored = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($name in (Invoke-GitText 'ls-files --cached --ignored --exclude-per-directory=.gitignore -z').Split([char]0, $splitOptions)) {
        [void]$ignored.Add($name)
    }
    $selected = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($name in $candidates) {
        if ($ignored.Contains($name) -or $name -eq '.git' -or $name.StartsWith('.git/')) { continue }
        $fullPath = [System.IO.Path]::GetFullPath((Join-Path $root $name))
        if (-not $fullPath.StartsWith($root + [System.IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            throw "文件路径超出项目目录：$name"
        }
        if ([string]::Equals($fullPath, $archivePath, [StringComparison]::OrdinalIgnoreCase)) { continue }
        # Ignore deleted tracked files; do not silently omit present submodules.
        if (-not (Test-Path -LiteralPath $fullPath)) { continue }
        $item = Get-Item -LiteralPath $fullPath -Force
        if ($item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            throw "文件列表包含子模块、符号链接或目录联接，无法安全打包：$name"
        }
        [void]$selected.Add($name)
    }
    $files = New-Object string[] $selected.Count
    $selected.CopyTo($files)
    [Array]::Sort($files, [StringComparer]::Ordinal)
    if ($files.Count -eq 0) { throw '没有找到可打包的项目文件。' }

    Write-Host "[2/3] 正在压缩 $($files.Count) 个文件，请耐心等待..."
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($archivePath))
    $archiveStream = [System.IO.File]::Open($archivePath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    $createdArchive = $true
    $archive = New-Object System.IO.Compression.ZipArchive($archiveStream, [System.IO.Compression.ZipArchiveMode]::Create, $false)
    foreach ($name in $files) {
        $entryName = 'LightSign/' + $name.Replace('\', '/')
        [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, (Join-Path $root $name), $entryName, [System.IO.Compression.CompressionLevel]::Optimal)
    }
    $archive.Dispose()
    $archive = $null
    $archiveStream.Dispose()
    $archiveStream = $null

    $size = (Get-Item -LiteralPath $archivePath).Length / 1MB
    Write-Host '[3/3] 打包完成！'
    Write-Host "  文件：$archivePath"
    Write-Host ('  大小：{0:N2} MB；包含 {1} 个文件。' -f $size, $files.Count)
    Write-Host '将 ZIP 发给对方，完整解压后双击 LightSign 文件夹内的 START.bat 即可。'
    exit 0
}
catch {
    if ($archive) { $archive.Dispose() }
    if ($archiveStream) { $archiveStream.Dispose() }
    if ($createdArchive -and [System.IO.File]::Exists($archivePath)) {
        [System.IO.File]::Delete($archivePath)
    }
    Write-Host "[错误] 打包失败：$($_.Exception.Message)" -ForegroundColor Red
    Write-Host '请检查 Git、项目目录权限和剩余磁盘空间，修复后重新运行。'
    exit 1
}
