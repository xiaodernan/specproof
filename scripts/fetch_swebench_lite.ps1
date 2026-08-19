<#
.SYNOPSIS
    Download SWE-bench-Lite instances as a local JSON file (offline-first usage).

.DESCRIPTION
    Fetches the princeton-nlp/SWE-bench_Lite dataset through the HuggingFace
    datasets-server "rows" API (no pip packages, no git-lfs) and writes one
    JSON array of instances to -OutFile. Instances use the SWE-bench-Lite
    schema consumed by scripts/bench_swebench.py:

        {instance_id, repo, base_commit, problem_statement, test_patch,
         FAIL_TO_PASS, PASS_TO_PASS, ...}

    Usage:
        .\scripts\fetch_swebench_lite.ps1                    # test split -> swebench-lite-test.json
        .\scripts\fetch_swebench_lite.ps1 -Split dev -OutFile .\swebench-dev.json
        .\scripts\fetch_swebench_lite.ps1 -Limit 10          # only the first 10 rows
        $env:HTTPS_PROXY = "http://127.0.0.1:7897"
        .\scripts\fetch_swebench_lite.ps1 -Proxy $env:HTTPS_PROXY

    Then run the harness:
        python scripts/bench_swebench.py --dataset .\swebench-lite-test.json --tasks 10

    Offline fallback: on ANY failure the script copies the bundled toy sample
    (scripts/swebench_sample/instances.json) to -OutFile so the harness stays
    testable without network, prints a clear message, and exits 1.

    Honesty notes:
        - This downloads the dataset JSON ONLY. It does NOT fetch the
          per-instance repositories, Docker images or install scripts; those
          are documented manual steps in docs/eval/SWEBENCH_PLAN.md.
        - The rows API paginates with max length=100, so a full 300-row split
          takes 3 requests; progress is reported with Write-Progress.
#>
[CmdletBinding()]
param(
    [ValidateSet("test", "dev")]
    [string]$Split = "test",

    [string]$OutFile = "swebench-lite-$Split.json",

    [string]$Proxy = $env:HTTPS_PROXY,

    [int]$Limit = 0
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # suppress Invoke-RestMethod's own bar
$Dataset = "princeton-nlp/SWE-bench_Lite"
$BaseUrl = "https://datasets-server.huggingface.co/rows"
$FallbackSample = Join-Path $PSScriptRoot "swebench_sample\instances.json"

function Write-OfflineFallback {
    param([string]$Failure)
    Write-Host ""
    Write-Host "下载失败: $Failure" -ForegroundColor Red
    Write-Host "离线回退: 复制捆绑样例 -> $OutFile" -ForegroundColor Yellow
    Write-Host "(样例仅验证 harness 机制; 它不是真实的 SWE-bench-Lite 数据。" -ForegroundColor Yellow
    Write-Host " 真实运行请修复网络/代理后重跑本脚本, 或手工准备数据集 JSON。)" -ForegroundColor Yellow
    try {
        $absoluteOut = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutFile)
        $outDir = Split-Path -Parent $absoluteOut
        if ($outDir -and -not (Test-Path -LiteralPath $outDir)) {
            New-Item -ItemType Directory -Path $outDir -Force | Out-Null
        }
        Copy-Item -LiteralPath $FallbackSample -Destination $absoluteOut -Force
        Write-Host "样例已复制到: $absoluteOut (可用 --dataset $absoluteOut 或 --offline 运行 harness)"
    }
    catch {
        Write-Host "离线回退也失败: $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Get-SwebenchRows {
    $allRows = @()
    $offset = 0
    $total = -1
    while ($total -lt 0 -or $offset -lt $total) {
        $remaining = if ($total -ge 0) { $total - $offset } else { 100 }
        $length = [math]::Min(100, $remaining)
        if ($Limit -gt 0) { $length = [math]::Min($length, $Limit - $allRows.Count) }
        if ($length -le 0) { break }

        $encoded = [uri]::EscapeDataString($Dataset)
        $query = '?dataset=' + $encoded + '&config=default&split=' + $Split + '&offset=' + $offset + '&length=' + $length
        $uri = $BaseUrl + $query
        $splat = @{ Uri = $uri; TimeoutSec = 60 }
        if ($Proxy) { $splat["Proxy"] = $Proxy }

        $response = Invoke-RestMethod @splat
        if ($null -eq $response) { throw "rows API 返回空响应 ($uri)" }
        if ($null -eq $response.rows) { throw "rows API 响应缺少 rows 字段 ($uri)" }
        if ($response.num_rows_total) { $total = [int]$response.num_rows_total }
        $allRows += @($response.rows | ForEach-Object { $_.row })
        $offset += $length

        if ($total -gt 0) {
            $pct = [math]::Min(100, [int](100 * $allRows.Count / $total))
            Write-Progress -Activity "下载 SWE-bench-Lite ($Split split)" -Status "$($allRows.Count)/$total 行" -PercentComplete $pct
        }
        if ($total -lt 0 -and @($response.rows).Count -lt $length) { break }
    }
    return $allRows
}

try {
    $rows = @(Get-SwebenchRows)
    if ($rows.Count -eq 0) { throw "rows API 返回 0 行 (split=$Split)" }
    $absoluteOut = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutFile)
    $outDir = Split-Path -Parent $absoluteOut
    if ($outDir -and -not (Test-Path -LiteralPath $outDir)) {
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    }
    $rows | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $absoluteOut -Encoding utf8
    Write-Host ""
    Write-Host "已下载 $($rows.Count) 个实例 -> $absoluteOut"
    Write-Host "注意: 仅数据集 JSON; 逐实例仓库 checkout / Docker 镜像仍需按"
    Write-Host "      docs/eval/SWEBENCH_PLAN.md 手工准备, harness 会诚实记录失败。"
    exit 0
}
catch {
    Write-OfflineFallback $_.Exception.Message
    exit 1
}
