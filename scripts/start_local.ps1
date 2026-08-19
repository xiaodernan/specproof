<#
.SYNOPSIS
  SpecProof 一键本地启动 (W43/W43.1): infra -> Worker/Outbox -> API -> seed -> Vite。
.DESCRIPTION
  幂等脚本: 已运行的容器/进程会被检测并跳过; 演示数据有稳定种子键, 重复执行不重复。
  验证管道 (Worker + Outbox Relay) 在 API 之前启动 (W43.1 要点), 种子
  保持在 API 之后 — Agent 演示任务必须经真实 POST /agent/jobs
  才带【演示】标题。worker/outbox 启动失败只警告不阻断
  (体验优先, 原因写入对应日志)。
  日志: .local\api.log / .local\web.log / .local\worker.log / .local\outbox.log。
.NOTES
  数据卷在 stop_local.ps1 中保留; 彻底重置请执行 docker compose -f compose.phase0.yml down -v。
#>
[CmdletBinding()]
param(
    # 可选 LLM 增强档: 读取会话环境变量 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL,
    # 注入后端/Worker 进程并重启已运行实例。变量缺失时回退确定性档。
    # 凭据只进环境变量, 本脚本绝不落盘任何 LLM 凭据。
    [switch]$WithLlm
)

$ErrorActionPreference = "Stop"

$RepoRoot     = Split-Path -Parent $PSScriptRoot
$LocalDir     = Join-Path $RepoRoot ".local"
$Compose      = Join-Path $RepoRoot "compose.phase0.yml"
$WebDir       = Join-Path $RepoRoot "apps\web"
$SeedScript   = Join-Path $RepoRoot "scripts\seed_demo.py"
$WorkerScript = Join-Path $RepoRoot "scripts\run_worker.py"

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

function Get-TrackedPid([string]$PidFile) {
    if (-not (Test-Path $PidFile)) { return $null }
    $raw = (Get-Content $PidFile -Raw).Trim()
    if (-not $raw) { return $null }
    return [int]$raw
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
$pythonPath = (Get-Command python).Source

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

# ── LLM 档位 (架构定性: 推理走远程 API, 其余全本地) ──
$LlmConfigured = $false
$llmModel = ""
if ($WithLlm) {
    $llmBase = [string]$env:LLM_BASE_URL
    $llmKey  = [string]$env:LLM_API_KEY
    $llmModel = [string]$env:LLM_MODEL
    if ($llmBase -and $llmKey) {
        Write-Ok "LLM 增强档: 使用本会话环境变量中的远程网关凭据 (仅内存, 不写入任何文件)"
        $LlmConfigured = $true
    } else {
        Write-WarnMsg "-WithLlm 已指定, 但 LLM_BASE_URL / LLM_API_KEY 环境变量不完整 — 回退确定性档 (浏览演示数据无需 LLM)"
    }
} else {
    Write-Ok "确定性档 (默认): 不依赖任何 LLM 环境变量, 演示数据完整体验无需密钥"
}

# ── 验证管道 (W43.1): worker -> outbox, 在 API 之前启动 ──
Write-Step "启动验证管道 (Worker + Outbox Relay — 新建验证任务从 QUEUED 走到终态)"
$workerPidFile = Join-Path $LocalDir "worker.pid"
$needWorkerStart = $false
if (Test-TrackedProcess $workerPidFile) {
    if ($WithLlm -and $LlmConfigured) {
        Write-Info "Worker 已在运行 — 按 LLM 增强档重启 Worker"
        $procId = Get-TrackedPid $workerPidFile
        if ($null -ne $procId) { & taskkill /PID $procId /T /F 2>$null | Out-Null }
        Remove-Item $workerPidFile -Force -ErrorAction SilentlyContinue
        $deadline = (Get-Date).AddSeconds(20)
        while ((Test-PortListening 9100) -and ((Get-Date) -lt $deadline)) {
            Start-Sleep -Seconds 2
        }
        $needWorkerStart = $true
    } else {
        Write-Ok "Worker 已在运行 (跳过启动)"
    }
} elseif (Test-PortListening 9100) {
    Write-WarnMsg "端口 9100 已被其他进程占用 — 跳过 Worker 启动 (可能已是其他实例)"
} else {
    $needWorkerStart = $true
}
if ($needWorkerStart) {
    try {
        $null = Start-TrackedProcess `
            -PidFile $workerPidFile `
            -OutLog (Join-Path $LocalDir "worker.log") `
            -ErrLog (Join-Path $LocalDir "worker.err") `
            -FilePath $pythonPath `
            -Arguments @($WorkerScript) `
            -WorkDir $RepoRoot
        Write-Info "Worker 启动中 (日志: .local\worker.log) ..."
        $deadline = (Get-Date).AddSeconds(60)
        while ((Get-Date) -lt $deadline) {
            if (Test-PortListening 9100) { break }
            Start-Sleep -Seconds 2
        }
        if (Test-PortListening 9100) {
            Write-Ok "Worker 就绪 (metrics 端口 9100)"
        } else {
            Write-WarnMsg "Worker 在 60 秒内未监听 9100 — 详情见 .local\worker.log (不阻断启动)"
        }
    } catch {
        Write-WarnMsg "Worker 启动失败 — 不阻断启动 (新建验证任务会停在 QUEUED), 原因: $($_.Exception.Message)"
        Add-Content -Path (Join-Path $LocalDir "worker.err") -Value "[start_local] worker start failed: $($_.Exception.Message)"
    }
}
$outboxPidFile = Join-Path $LocalDir "outbox.pid"
$needOutboxStart = $false
if (Test-TrackedProcess $outboxPidFile) {
    Write-Ok "Outbox Relay 已在运行 (跳过启动)"
} elseif (Test-PortListening 9101) {
    Write-WarnMsg "端口 9101 已被其他进程占用 — 跳过 Outbox Relay 启动 (可能已是其他实例)"
} else {
    $needOutboxStart = $true
}
if ($needOutboxStart) {
    try {
        $null = Start-TrackedProcess `
            -PidFile $outboxPidFile `
            -OutLog (Join-Path $LocalDir "outbox.log") `
            -ErrLog (Join-Path $LocalDir "outbox.err") `
            -FilePath $pythonPath `
            -Arguments @("-m", "storage.outbox_relay") `
            -WorkDir $RepoRoot
        Write-Info "Outbox Relay 启动中 (日志: .local\outbox.log) ..."
    } catch {
        Write-WarnMsg "Outbox Relay 启动失败 — 不阻断启动 (新建验证任务会停在 QUEUED), 原因: $($_.Exception.Message)"
        Add-Content -Path (Join-Path $LocalDir "outbox.err") -Value "[start_local] outbox relay start failed: $($_.Exception.Message)"
    }
}

# ── API ──
Write-Step "启动 FastAPI (uvicorn api.server:app -> $ApiUrl)"
$apiPidFile = Join-Path $LocalDir "api.pid"
$needApiStart = $false
if (Test-TrackedProcess $apiPidFile) {
    if ($WithLlm -and $LlmConfigured) {
        Write-Info "API 已在运行 — 按 LLM 增强档重启后端 (环境变量变更后必须重启才生效)"
        $procId = Get-TrackedPid $apiPidFile
        if ($null -ne $procId) { & taskkill /PID $procId /T /F 2>$null | Out-Null }
        Remove-Item $apiPidFile -Force -ErrorAction SilentlyContinue
        $deadline = (Get-Date).AddSeconds(20)
        while ((Test-PortListening 8000) -and ((Get-Date) -lt $deadline)) {
            Start-Sleep -Seconds 2
        }
        if (Test-PortListening 8000) {
            Write-Host "端口 8000 未及时释放 — 无法重启后端。" -ForegroundColor Red
            exit 1
        }
        $needApiStart = $true
    } else {
        Write-Ok "API 已在运行 (跳过启动)"
    }
} elseif (Test-PortListening 8000) {
    if ($WithLlm -and $LlmConfigured) {
        Write-WarnMsg "端口 8000 被非本脚本管理的进程占用 — 无法安全重启, 跳过 (请先处理该进程或运行 stop_local.ps1)"
    } else {
        Write-WarnMsg "端口 8000 已被其他进程占用 — 跳过 API 启动 (若密钥不匹配, 种子会自动走存储回退)"
    }
} else {
    $needApiStart = $true
}
if ($needApiStart) {
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

# ── 种子数据 (保持 API 之后: Agent 演示任务需真实 POST 才带【演示】标题) ──
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
if ($LlmConfigured) {
    Write-Host "  档位       : LLM 增强档 (模型: $llmModel; 凭据仅存在于本会话环境变量, 未写入任何文件)"
} else {
    Write-Host "  档位       : 确定性档 (未注入 LLM 凭据, 演示数据浏览与审批流完整可用)"
}
Write-Host "  Web 前端   : $WebUrl           <- 从这里开始"
Write-Host "  API 文档   : $ApiUrl/docs"
Write-Host "  登录密钥   : $DemoApiKey   (登录页选择 X-API-Key)"
Write-Host "  日志       : .local\api.log / .local\web.log / .local\worker.log / .local\outbox.log"
Write-Host "  停止       : pwsh scripts\stop_local.ps1"
Write-Host ""
Write-Host "  第一步: 打开 $WebUrl -> 粘贴密钥 -> 总览看到 3 条【演示】验证任务"
Write-Host "          -> 点进【演示】AUTH 越权回归 -> Findings / 证书;"
Write-Host "          再到 Agent 页审批【演示】修复 double 函数 的计划与门禁"
Write-Host ""
exit 0
