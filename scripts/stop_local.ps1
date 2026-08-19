<#
.SYNOPSIS
  SpecProof 本地体验停止脚本 (W43/W43.1): 停前端/后端/Worker/Outbox 进程树 + compose down (数据卷保留)。
.DESCRIPTION
  只停止由 start_local.ps1 记录在 .local\*.pid 的进程树;
  不会杀掉未知的端口占用进程。容器执行 compose down
  而不带 -v, 因此 MySQL/Mongo/ES/Redis/RabbitMQ/MinIO 数据全部保留。
.NOTES
  彻底重置演示数据: docker compose -f compose.phase0.yml down -v
#>
[CmdletBinding()]
param()

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LocalDir = Join-Path $RepoRoot ".local"
$Compose  = Join-Path $RepoRoot "compose.phase0.yml"

function Stop-Tracked([string]$PidFile, [string]$Label) {
    if (-not (Test-Path $PidFile)) {
        Write-Host "    [skip] $Label 没有 PID 记录 (未由 start_local.ps1 启动)"
        return
    }
    $raw = (Get-Content $PidFile -Raw).Trim()
    if ($raw) {
        $procId = [int]$raw
        & taskkill /PID $procId /T /F 2>$null | Out-Null
        Write-Host "    [ok] 已停止 $Label (PID $procId, 含子进程)"
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

Write-Host "==> 停止本地体验 (数据卷保留)" -ForegroundColor Cyan
Stop-Tracked (Join-Path $LocalDir "web.pid") "前端 Vite"
Stop-Tracked (Join-Path $LocalDir "api.pid") "后端 FastAPI"
Stop-Tracked (Join-Path $LocalDir "worker.pid") "验证 Worker"
Stop-Tracked (Join-Path $LocalDir "outbox.pid") "Outbox Relay"

Write-Host "==> 停止基础设施容器" -ForegroundColor Cyan
try {
    & docker compose -f $Compose down
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    [ok] compose down 完成 — 数据卷已保留, 下次启动数据仍在" -ForegroundColor Green
    } else {
        Write-Host "    [warn] compose down 退出码 $LASTEXITCODE (Docker 未运行?)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "    [warn] docker 不可用, 跳过 compose down: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  彻底重置演示数据: docker compose -f compose.phase0.yml down -v  (会删除全部数据卷)"
Write-Host "  再次启动: pwsh scripts\start_local.ps1"
