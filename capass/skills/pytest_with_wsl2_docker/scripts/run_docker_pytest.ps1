<#
.SYNOPSIS
    WSL2 + Docker コンテナを用いて、ホスト環境を汚さずに pytest を実行するヘルパースクリプト。

.PARAMETER ZipPath
    テスト対象のソースコード zip ファイルの Windows パス。
    省略した場合は、プロジェクトルートのソースツリーを直接テストします。

.PARAMETER Target
    テスト対象のサブパッケージ ('toolserver' または 'server')。デフォルトは 'toolserver'。

.PARAMETER Image
    使用する Docker イメージ。デフォルトは 'python:3.11-slim'。
#>

param(
    [string]$ZipPath = "",
    [ValidateSet("toolserver", "server")]
    [string]$Target = "toolserver",
    [string]$Image = "python:3.11-slim"
)

$ErrorActionPreference = "Stop"

# Windows パスを WSL パスに変換するヘルパー関数
function ConvertTo-WslPath([string]$winPath) {
    if ([string]::IsNullOrWhiteSpace($winPath)) { return "" }
    $resolved = (Resolve-Path $winPath).Path
    $drive = $resolved.Substring(0, 1).ToLower()
    $rest = $resolved.Substring(2).Replace('\', '/')
    return "/mnt/$drive$rest"
}

$workspaceWin = (Resolve-Path "$PSScriptRoot\..").Path
$workspaceWsl = ConvertTo-WslPath $workspaceWin

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " WSL2 Docker pytest Runner" -ForegroundColor Cyan
Write-Host " Target: $Target | Image: $Image" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

if ($ZipPath -ne "") {
    if (-not (Test-Path $ZipPath)) {
        Write-Error "Zip file not found: $ZipPath"
        exit 1
    }
    $zipWsl = ConvertTo-WslPath $ZipPath
    $zipName = Split-Path $ZipPath -Leaf
    Write-Host "Testing from zip archive: $ZipPath" -ForegroundColor Green

    if ($Target -eq "toolserver") {
        $cmd = "python -m zipfile -e /tmp/in.zip /tmp/src && " +
               "ROOT=`$(ls -d /tmp/src/* | head -n 1) && " +
               "pip install --no-cache-dir -e `"`$ROOT/core`" && " +
               "pip install --no-cache-dir -e `"`$ROOT/toolserver[dev]`" && " +
               "pytest -vv -p no:cacheprovider `"`$ROOT/toolserver/tests`""

        wsl docker run --rm `
            -v "${zipWsl}:/tmp/in.zip:ro" `
            -v "${workspaceWsl}:/workspace" `
            -w /workspace `
            -e PYTHONDONTWRITEBYTECODE=1 `
            $Image `
            sh -c $cmd
    }
    elseif ($Target -eq "server") {
        # サーバー用環境変数（Fernet 暗号化鍵はコンテナ内部で動的生成）
        $cmd = "export CAPASS_SERVER_TOKEN_ENCRYPTION_KEYS=`$(python3 -c 'import base64,secrets;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())') && " +
               "python -m zipfile -e /tmp/in.zip /tmp/src && " +
               "ROOT=`$(ls -d /tmp/src/* | head -n 1) && " +
               "pip install --no-cache-dir -e `"`$ROOT/server[dev]`" && " +
               "pytest -vv -p no:cacheprovider `"`$ROOT/server/tests`""

        wsl docker run --rm `
            -v "${zipWsl}:/tmp/in.zip:ro" `
            -v "${workspaceWsl}:/workspace" `
            -w /workspace `
            -e PYTHONDONTWRITEBYTECODE=1 `
            -e CAPASS_SERVER_ENV=LOCAL_DEV `
            -e CAPASS_SERVER_DB_HOST=127.0.0.1 `
            -e CAPASS_SERVER_DB_PORT=5432 `
            -e CAPASS_SERVER_DB_NAME=capass `
            -e CAPASS_SERVER_DB_USER=capass `
            -e CAPASS_SERVER_DB_PASSWORD=capass `
            $Image `
            sh -c $cmd
    }
}
else {
    # リポジトリ直接テスト (capass ルート)
    $repoRootWin = (Resolve-Path "$PSScriptRoot\..\..\..").Path
    $repoRootWsl = ConvertTo-WslPath $repoRootWin
    Write-Host "Testing from repository tree: $repoRootWin" -ForegroundColor Green

    if ($Target -eq "toolserver") {
        $cmd = "pip install --no-cache-dir -e ./core && " +
               "pip install --no-cache-dir -e ./toolserver[dev] && " +
               "pytest -vv -p no:cacheprovider ./toolserver/tests"

        wsl docker run --rm `
            -v "${repoRootWsl}:/workspace" `
            -w /workspace `
            -e PYTHONDONTWRITEBYTECODE=1 `
            $Image `
            sh -c $cmd
    }
    elseif ($Target -eq "server") {
        $cmd = "export CAPASS_SERVER_TOKEN_ENCRYPTION_KEYS=`$(python3 -c 'import base64,secrets;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())') && " +
               "pip install --no-cache-dir -e ./server[dev] && " +
               "pytest -vv -p no:cacheprovider ./server/tests"

        wsl docker run --rm `
            -v "${repoRootWsl}:/workspace" `
            -w /workspace `
            -e PYTHONDONTWRITEBYTECODE=1 `
            -e CAPASS_SERVER_ENV=LOCAL_DEV `
            -e CAPASS_SERVER_DB_HOST=127.0.0.1 `
            -e CAPASS_SERVER_DB_PORT=5432 `
            -e CAPASS_SERVER_DB_NAME=capass `
            -e CAPASS_SERVER_DB_USER=capass `
            -e CAPASS_SERVER_DB_PASSWORD=capass `
            $Image `
            sh -c $cmd
    }
}
