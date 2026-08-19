<#
.SYNOPSIS
    Download https://www.swebench.com and save the embedded leaderboard JSON.

.DESCRIPTION
    The swebench.com homepage ships its leaderboard data as an embedded
    <script type="application/json"> blob: an array of benchmark views, each
    {"name": ..., "results": [...]} where every result row carries
    agent / model / resolved / cost / date (plus per-instance details).

    This script:
      1. downloads the page through the local proxy (default
         http://127.0.0.1:7897; overridable via -Proxy or $env:HTTPS_PROXY),
      2. locates the application/json script tag,
      3. validates that the blob contains a "Verified" view whose results are
         non-empty and carry agent/resolved/date fields, and
      4. writes the raw blob to docs/eval/swebench-leaderboard-raw.json.

    Honesty: if the page structure changed and no valid blob can be found, the
    script prints a clear failure note and exits 1 WITHOUT writing or
    overwriting the output file. Nothing is fabricated.

    Usage:
        powershell -File scripts/fetch_swebench_leaderboard.ps1
        powershell -File scripts/fetch_swebench_leaderboard.ps1 -Proxy http://127.0.0.1:7897
        powershell -File scripts/fetch_swebench_leaderboard.ps1 -NoProxy -Url http://localhost:8000/snapshot.html -OutFile .\probe.json

    Then summarize:
        python scripts/summarize_leaderboard.py
#>
[CmdletBinding()]
param(
    [string]$Url = "https://www.swebench.com",

    [string]$OutFile = "",

    [string]$Proxy = $env:HTTPS_PROXY,

    [switch]$NoProxy,

    [int]$TimeoutSec = 90
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if (-not $OutFile) {
    $OutFile = Join-Path $PSScriptRoot "..\docs\eval\swebench-leaderboard-raw.json"
}
$absoluteOut = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutFile)
$outDir = Split-Path -Parent $absoluteOut

function Write-FailureNote {
    param([string]$Failure)

    Write-Host ""
    Write-Host "== SWE-bench leaderboard fetch FAILED (no file written) ==" -ForegroundColor Red
    Write-Host "Reason: $Failure" -ForegroundColor Red
    Write-Host "Either the page structure at $Url changed, the proxy is unreachable,"
    Write-Host "or the network request failed. No leaderboard JSON was written or"
    Write-Host "overwritten; nothing is fabricated."
    Write-Host "Retry later with: powershell -File scripts/fetch_swebench_leaderboard.ps1"
}

function Find-EmbeddedLeaderboard {
    param([string]$Html)

    # Attribute order varies, so match the tag with a permissive regex.
    $tagPattern = '<script\b[^>]*\btype\s*=\s*["'']application/json["''][^>]*>'
    $options = [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    $tags = [regex]::Matches($Html, $tagPattern, $options)
    if ($tags.Count -eq 0) {
        throw 'no <script type="application/json"> tag found in the downloaded page'
    }

    foreach ($tag in $tags) {
        $start = $tag.Index + $tag.Length
        $end = $Html.IndexOf('</script>', $start, [System.StringComparison]::OrdinalIgnoreCase)
        if ($end -lt 0) { continue }
        $jsonText = $Html.Substring($start, $end - $start).Trim()
        if ([string]::IsNullOrWhiteSpace($jsonText)) { continue }

        try {
            $parsed = $jsonText | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            continue
        }

        $verified = $null
        foreach ($item in @($parsed)) {
            if ($null -ne $item -and $item.name -eq "Verified") {
                $verified = $item
                break
            }
        }
        if ($null -eq $verified) { continue }

        $results = @($verified.results)
        if ($results.Count -eq 0) { continue }

        $first = $results[0]
        if ($null -eq $first.agent -or $null -eq $first.resolved -or $null -eq $first.date) {
            continue
        }

        return @{ JsonText = $jsonText; Parsed = $parsed }
    }

    throw "no application/json script containing a valid 'Verified' leaderboard view was found"
}

try {
    $splat = @{ Uri = $Url; TimeoutSec = $TimeoutSec }
    if ($NoProxy) {
        Write-Host "Fetching $Url (direct connection, no proxy) ..."
    }
    else {
        if (-not $Proxy) { $Proxy = "http://127.0.0.1:7897" }
        $splat["Proxy"] = $Proxy
        Write-Host "Fetching $Url via proxy $Proxy ..."
    }

    $response = Invoke-WebRequest @splat -UseBasicParsing -UserAgent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) specproof-swebench-leaderboard-fetch/1.0"
    if ($null -eq $response.Content -or [string]::IsNullOrWhiteSpace($response.Content)) {
        throw "page returned empty content (HTTP $($response.StatusCode))"
    }
    Write-Host ("Downloaded " + $response.Content.Length + " characters (HTTP " + $response.StatusCode + ").")

    $found = Find-EmbeddedLeaderboard $response.Content

    if (-not (Test-Path -LiteralPath $outDir)) {
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($absoluteOut, $found.JsonText, $utf8NoBom)

    $benchmarks = @()
    foreach ($item in @($found.Parsed)) {
        if ($null -ne $item -and $null -ne $item.name) {
            $count = if ($null -ne $item.results) { @($item.results).Count } else { 0 }
            $benchmarks += ($item.name + " (" + $count + ")")
        }
    }

    Write-Host ""
    Write-Host "OK: raw leaderboard JSON saved -> $absoluteOut" -ForegroundColor Green
    Write-Host ("Embedded benchmark views: " + ($benchmarks -join ", "))
    Write-Host "Next: python scripts/summarize_leaderboard.py"
    exit 0
}
catch {
    Write-FailureNote $_.Exception.Message
    exit 1
}
