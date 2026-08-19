<#
.SYNOPSIS
  SpecProof 一键本地启动 (W43): 基础设施 -> API -> 演示数据 -> Web -> 打印入口。
.DESCRIPTION
  幂等脚本: 已运行的容器/进程会被检测并跳过; 演示数据有稳定种子键, 重复执行不会重复。
  日志: .local\api.log / .local\web.log (每次启动覆盖, 保留最近一次启动的输出)。
.NOTES
  数据卷在 stop_local.ps1 中保留; 彻底重置请执行 docker compose -f compose.phase0.yml down -v。
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$RepoRoot   = Split-Path -Parent $PSScriptRoot
$LocalDir   = Join-Path $RepoRoot ".local"
$Compose    = Join-Path $RepoRoot "compose.phase0.yml"
$WebDir     = Join-Path $RepoRoot "apps\web"
$SeedScript = Join-Path $RepoRoot "scripts\seed_demo.py"

$ApiUrl     = "http://127.0.0.1:8000"
$WebUrl     = "http://localhost:5173"
$DemoApiKey = "specproof-local-demo-key"

function Write-Step([string]$Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}
function Write-Ok([string]$Message) {
    Write-Host "    [ok] $Message" -ForegroundColor Green
}
function Write-Info([string]$Message) {
    Write-Host "    [..] $Message" -ForegroundColor DarkGray
}
function Write-WarnMsg([string]$Message) {
    Write-Warning "    $Message"
}

function Test-Command([string]$Name) {
    return ($null -ne (Get-Command $Name -ErrorAction SilentlyContinue))
}

function Test-PortListening([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return ($null -ne $listener)
}

function Test-TrackedProcess([string]$PidFile) {
    if (-not (Test-Path $PidFile)) { return $false }
    $raw = (Get-Content $PidFile -Raw).Trim()
    if (-not $raw) {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        return $false
    }
    $procId = [int]$raw
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($null -eq $proc) {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        return $false
    }
    return $true
}

function Test-ContainerHealthy([string]$Container) {
    $status = (& docker inspect -f "{{.State.Health.Status}}" $Container 2>$null | Out-String).Trim()
    return ($status -eq "healthy")
}

function Wait-ContainerHealthy([string]$Container, [int]$TimeoutSec, [string]$Label) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-ContainerHealthy $Container) {
            Write-Ok "$Label ($Container) 已就绪"
            return $true
        }
        Start-Sleep -Seconds 5
    }
    Write-WarnMsg "$Label ($Container) 在 $TimeoutSec 秒内未就绪"
    return $false
}

function Start-TrackedProcess([string]$PidFile, [string]$OutLog, [string]$ErrLog,
                              [string]$FilePath, [string[]]$Arguments, [string]$WorkDir) {
    if (Test-TrackedProcess $PidFile) {
        return $false
    }
    $proc = Start-Process -FilePath $FilePath `
        -ArgumentList $Arguments `
        -WorkingDirectory $WorkDir `
        -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog `
        -PassThru -WindowStyle Hidden
    Set-Content -Path $PidFile -Value $proc.Id -Encoding Ascii
    return $true
}

function Wait-ApiReady([int]$TimeoutSec) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $null = Invoke-RestMethod -Uri "$ApiUrl/health" -TimeoutSec 3
            return $true
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    return $false
}

# ── 预检 ──
Write-Step "预检: 检查本机工具链"
$missing = @()
foreach ($tool in @("docker", "python", "node", "npm")) {
    if (-not (Test-Command $tool)) { $missing += $tool }
}
if ($missing.Count -gt 0) {
    Write-Host "缺少以下命令, 请先安装并加入 PATH: $($missing -join ', ')" -ForegroundColor Red
    Write-Host "参见 docs/operations/LOCAL_EXPERIENCE.md 的前提条件章节" -ForegroundColor Yellow
    exit 1
}
Write-Ok "docker / python / node / npm 均可用"

Write-Step "检查 Docker Desktop"
try {
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) { throw "docker info 失败" }
} catch {
    Write-Host "Docker 不可用 (未启动或未安装)。请先启动 Docker Desktop。" -ForegroundColor Red
    exit 1
}
Write-Ok "Docker 可用"

# ── 基础设施 ──
Write-Step "启动基础设施容器 (compose.phase0.yml)"
New-Item -ItemType Directory -Force -Path $LocalDir | Out-Null
& docker compose -f $Compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "docker compose up 失败 (退出码 $LASTEXITCODE)。常见原因: 端口被占用 (3306/9200/6379/5672/9000/27017) 或镜像拉取失败。" -ForegroundColor Red
    exit 1
}

Write-Step "等待容器健康检查 (首次需拉取镜像, 可能需要几分钟)"
if (-not (Wait-ContainerHealthy "specproof-mysql" 300 "MySQL")) {
    Write-Host "MySQL 未就绪 — API 与演示验证任务都依赖它, 无法继续。" -ForegroundColor Red
    Write-Host "排查: docker ps -a; docker logs specproof-mysql" -ForegroundColor Yellow
    exit 1
}
$null = Wait-ContainerHealthy "specproof-elasticsearch" 300 "Elasticsearch"
$null = Wait-ContainerHealthy "specproof-redis" 120 "Redis"
$null = Wait-ContainerHealthy "specproof-mongodb" 120 "MongoDB"
$null = Wait-ContainerHealthy "specproof-rabbitmq" 120 "RabbitMQ"
$null = Wait-ContainerHealthy "specproof-minio" 120 "MinIO"

# ── API 环境变量 ──
Write-Step "配置 API 环境变量 (演示密钥, 仅本机演示用)"
$env:SPECPROOF_API_KEY  = $DemoApiKey
$env:SPECPROOF_API_BASE = $ApiUrl
if (Test-ContainerHealthy "specproof-mysql") {
    $env:SPECPROOF_AGENT_JOBS_URL = "mysql+pymysql://specproof:specproof_pass@localhost:3306/specproof_phase0"
    Write-Ok "Agent 任务存储: MySQL (与 API 相同)"
} else {
    $env:SPECPROOF_AGENT_JOBS_URL = "sqlite:" + (Join-Path $LocalDir "specproof_agent_jobs.db")
    Write-WarnMsg "Agent 任务存储回退: SQLite (.local\specproof_agent_jobs.db)"
}

# ── API ──
Write-Step "启动 FastAPI (uvicorn api.server:app -> $ApiUrl)"
$apiPidFile = Join-Path $LocalDir "api.pid"
if (Test-TrackedProcess $apiPidFile) {
    Write-Ok "API 已在运行 (跳过启动)"
} elseif (Test-PortListening 8000) {
    Write-WarnMsg "端口 8000 已被其他进程占用 — 跳过 API 启动 (若密钥不匹配, 种子会自动走存储回退)"
} else {
    $pythonPath = (Get-Command python).Source
    $null = Start-TrackedProcess `
        -PidFile $apiPidFile `
        -OutLog (Join-Path $LocalDir "api.log") `
        -ErrLog (Join-Path $LocalDir "api.err") `
        -FilePath $pythonPath `
        -Arguments @("-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", "8000") `
        -WorkDir $RepoRoot
    Write-Info "API 启动中 (日志: .local\api.log) ..."
    if (-not (Wait-ApiReady 90)) {
        Write-Host "API 在 90 秒内未就绪。检查 .local\api.log (常见: 未执行 pip install -e '.[dev]')" -ForegroundColor Red
        exit 1
    }
    Write-Ok "API 就绪: $ApiUrl/health"
}

# ── 种子数据 ──
Write-Step "播种演示数据 (幂等, 可重复执行)"
& python $SeedScript --api-base $ApiUrl --api-key $DemoApiKey
if ($LASTEXITCODE -ne 0) {
    Write-WarnMsg "seed 脚本退出码 $LASTEXITCODE — 继续启动前端 (请查看上方输出)"
}

# ── 前端 ──
Write-Step "启动前端 (Vite dev server -> $WebUrl)"
if (-not (Test-Path (Join-Path $WebDir "node_modules"))) {
    Write-Info "首次运行: 在 apps/web 执行 npm install (需要几分钟) ..."
    Push-Location $WebDir
    try {
        & npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install 失败 (退出码 $LASTEXITCODE)" }
    } finally {
        Pop-Location
    }
    Write-Ok "npm install 完成"
}
$webPidFile = Join-Path $LocalDir "web.pid"
if (Test-TrackedProcess $webPidFile) {
    Write-Ok "前端已在运行 (跳过启动)"
} elseif (Test-PortListening 5173) {
    Write-WarnMsg "端口 5173 已被其他进程占用 — 跳过前端启动"
} else {
    # Get-Command npm 可能解析到 npm.ps1 (Start-Process 无法执行),
    # 因此优先使用 Node 自带的 npm.cmd 批处理文件。
    $npmPath = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
    if (-not $npmPath) { $npmPath = (Get-Command npm).Source }
    $null = Start-TrackedProcess `
        -PidFile $webPidFile `
        -OutLog (Join-Path $LocalDir "web.log") `
        -ErrLog (Join-Path $LocalDir "web.err") `
        -FilePath $npmPath `
        -Arguments @("run", "dev") `
        -WorkDir $WebDir
    Write-Info "Vite 启动中 (日志: .local\web.log) ..."
}

# ── 总结 ──
Write-Step "全部就绪"
Write-Host ""
Write-Host "  Web 前端   : $WebUrl           <- 从这里开始"
Write-Host "  API 文档   : $ApiUrl/docs"
Write-Host "  登录密钥   : $DemoApiKey   (登录页选择 X-API-Key)"
Write-Host "  日志       : .local\api.log / .local\web.log"
Write-Host "  停止       : pwsh scripts\stop_local.ps1"
Write-Host ""
Write-Host "  第一步: 打开 $WebUrl -> 粘贴密钥 -> 总览看到 3 条【演示】验证任务"
Write-Host "          -> 点进【演示】AUTH 越权回归 -> Findings / 证书;"
Write-Host "          再到 Agent 页审批【演示】修复 double 函数 的计划与门禁"
Write-Host ""
exit 0
