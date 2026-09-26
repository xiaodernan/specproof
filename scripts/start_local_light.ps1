<#
.SYNOPSIS
  SpecProof 轻量本地启动 (Phase 1.2): 零 Docker, 30 秒进入工作台。
.DESCRIPTION
  只依赖 Python 3.12 与 Node 18+, 不启动 docker-compose, 不要求 MySQL/Redis/
  RabbitMQ/Mongo/MinIO。后端使用可持久化的 SQLite 作业库 + SQLite 对象元数据,
  前端为 Vite 开发服务器。

  适用: 首次体验工作台、上手指南、AI 开发助手 (Craft 以进程内线程运行, 无需消息
  队列)、模型连接配置、浏览历史与需求矩阵。

  不适用 (请用 scripts/start_local.ps1 全栈模式): 需要 RabbitMQ + Worker 的
  Java/Spring 差分验收任务投递, 以及多租户团队部署。

  幂等: 已运行的受跟踪进程会被跳过; 用 -Restart 强制重启; 停止用 stop_local.ps1
  或读取 .local\*.pid。日志在 .local\api-light.log / .local\web-light.log。
.EXAMPLE
  pwsh scripts/start_local_light.ps1
  pwsh scripts/start_local_light.ps1 -Restart
#>
[CmdletBinding()]
param(
    [switch]$Restart,
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LocalDir = Join-Path $RepoRoot ".local"
$WebDir   = Join-Path $RepoRoot "apps\web"

$ApiUrl     = "http://127.0.0.1:$ApiPort"
$WebUrl     = "http://localhost:$WebPort"
# 本地工作区访问密钥, 不是模型密钥。可用环境变量 SPECPROOF_API_KEY 覆盖。
$DemoApiKey = if ($env:SPECPROOF_API_KEY) { $env:SPECPROOF_API_KEY } else { "specproof-local-demo-key" }

function Write-Step([string]$m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Ok([string]$m)   { Write-Host "    [ok] $m" -ForegroundColor Green }
function Write-WarnMsg([string]$m) { Write-Warning "    $m" }

if (-not (Test-Path $LocalDir)) { New-Item -ItemType Directory -Path $LocalDir | Out-Null }

$Python      = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Step "未找到 .venv, 使用系统 python (请先执行: python -m venv .venv && .venv/Scripts/python -m pip install -e '.[dev]')"
    $Python = "python"
}

$JobsDb     = Join-Path $LocalDir "light-jobs.sqlite3"
$MetadataDb = Join-Path $LocalDir "light-object-metadata.sqlite3"

# ── 轻量后端环境变量: 全部落 SQLite, 零外部服务 ──
# 显式声明这不是生产环境 (config_guard 只在 SPECPROOF_ENV=production 时拒绝默认口令)。
$env:SPECPROOF_ENV                   = "dev"
$env:SPECPROOF_API_KEY               = $DemoApiKey
$env:SPECPROOF_AGENT_JOBS_URL        = "sqlite:$JobsDb"
$env:SPECPROOF_AGENT_CONSOLE_URL     = "sqlite:$JobsDb"
$env:SPECPROOF_OBJECT_METADATA_DB    = $MetadataDb
# 未显式指向 MySQL 时, 对象元数据默认已是 SQLite; 这里再兜底, 避免误触 Docker 后端。
if (-not $env:SPECPROOF_OBJECT_METADATA_BACKEND) { $env:SPECPROOF_OBJECT_METADATA_BACKEND = "" }

function Stop-Tracked([string]$PidFile) {
    if (-not (Test-Path $PidFile)) { return }
    $raw = (Get-Content $PidFile -Raw).Trim()
    if ($raw) {
        Get-Process -Id ([int]$raw) -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

function Start-Tracked([string]$PidFile, [string]$OutLog, [string]$ErrLog,
                       [string]$FilePath, [string[]]$Arguments, [string]$WorkDir) {
    if ((Test-Path $PidFile) -and (Get-Process -Id ([int]((Get-Content $PidFile -Raw).Trim())) -ErrorAction SilentlyContinue)) {
        if ($Restart) { Stop-Tracked $PidFile } else { return $false }
    }
    $proc = Start-Process -FilePath $FilePath -ArgumentList $Arguments `
        -WorkingDirectory $WorkDir -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog -PassThru -WindowStyle Hidden
    Set-Content -Path $PidFile -Value $proc.Id -Encoding Ascii
    return $true
}

function Wait-ApiReady([int]$TimeoutSec) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $null = Invoke-RestMethod -Uri "$ApiUrl/health" -TimeoutSec 3
            return $true
        } catch { Start-Sleep -Seconds 2 }
    }
    return $false
}

if ($Restart) {
    Write-Step "重启: 停止已跟踪的轻量进程"
    Stop-Tracked (Join-Path $LocalDir "api-light.pid")
    Stop-Tracked (Join-Path $LocalDir "web-light.pid")
}

# ── 1. API ──
Write-Step "启动 FastAPI (uvicorn api.server:app -> $ApiUrl, SQLite 后端)"
$apiStarted = Start-Tracked `
    (Join-Path $LocalDir "api-light.pid") `
    (Join-Path $LocalDir "api-light.log") `
    (Join-Path $LocalDir "api-light.err") `
    $Python @("-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", "$ApiPort") $RepoRoot
if ($apiStarted) { Write-Ok "API 进程已启动" } else { Write-Ok "API 已在运行, 跳过" }

if (-not (Wait-ApiReady 60)) {
    Write-WarnMsg "API 未在 60 秒内就绪。查看日志: .local\api-light.err / .local\api-light.log"
} else {
    Write-Ok "API 就绪: $ApiUrl/health"
}

# ── 2. 前端 ──
Write-Step "启动 Vite 前端 (-> $WebUrl)"
$npm = if (Get-Command npm -ErrorAction SilentlyContinue) { "npm" } else { $null }
if (-not $npm) {
    Write-WarnMsg "未找到 npm。请安装 Node 18+ 后重跑, 或手动执行: cd apps/web && npm install && npm run dev"
} else {
    if (-not (Test-Path (Join-Path $WebDir "node_modules"))) {
        Write-Step "首次安装前端依赖 (npm install)"
        & $npm install --prefix $WebDir
    }
    $webStarted = Start-Tracked `
        (Join-Path $LocalDir "web-light.pid") `
        (Join-Path $LocalDir "web-light.log") `
        (Join-Path $LocalDir "web-light.err") `
        "cmd.exe" @("/c", "npm", "run", "dev", "--", "--port", "$WebPort") $WebDir
    if ($webStarted) { Write-Ok "Vite 进程已启动" } else { Write-Ok "Vite 已在运行, 跳过" }
}

# ── 演示仓库 git 版本 (幂等) ──
# 轻量模式下网页版差分验收需要 MySQL/Redis (会返回 503), 故这里为「推荐的命令行
# 回退」(specproof demo / verify) 预置 base / head-v1 引用。prepare_demo_repo 已存在
# 引用时跳过、不改工作区; git 缺失或失败仅告警, 不阻断启动。
Write-Step "准备演示仓库 git 版本 (base / head-v1, 幂等)"
if (Get-Command git -ErrorAction SilentlyContinue) {
    try {
        & $Python -c "from cli.specproof.commands.demo import prepare_demo_repo; print('created' if prepare_demo_repo() else 'exists')"
        if ($LASTEXITCODE -ne 0) { throw "prepare_demo_repo 退出码 $LASTEXITCODE" }
        Write-Ok "演示仓库 git 版本就绪 (base / head-v1)"
    } catch {
        Write-WarnMsg "演示仓库准备失败 — 命令行 specproof demo 仍可用 (需 Python 3.12 与 git)。原因: $($_.Exception.Message)"
    }
} else {
    Write-WarnMsg "未检测到 git — 跳过演示仓库准备"
}

Write-Host ""
Write-Host "SpecProof 轻量模式已启动 (无 Docker)。" -ForegroundColor Green
Write-Host "  打开工作台: $WebUrl"
Write-Host "  工作区访问密钥: $DemoApiKey"
Write-Host "  首次进入先看『上手指南』。数据落在 .local\light-jobs.sqlite3, 完全本机, 与全栈模式互不影响。"
Write-Host ""
Write-Host "  说明: 轻量模式支持工作台/AI 开发助手/模型连接/浏览历史。" -ForegroundColor DarkGray
Write-Host "  需要 Java/Spring 差分验收任务 (RabbitMQ + Worker) 时, 请用 scripts/start_local.ps1 全栈模式。" -ForegroundColor DarkGray
Write-Host "  停止: pwsh scripts/stop_local.ps1 (或读取 .local\*-light.pid 结束进程)。" -ForegroundColor DarkGray
