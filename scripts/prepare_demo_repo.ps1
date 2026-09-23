<#
.SYNOPSIS
  准备 SpecProof 演示仓库 (demo/spring-backend) 供「变更验收」真实体验。

.DESCRIPTION
  演示仓库在源码包中不带 .git。本脚本把它初始化为一个本地 git 仓库,
  并创建两个引用:
    base            原始实现 (需求要求的权限检查完整)
    head-v1     移除了 changeEmail 的 @PreAuthorize 权限检查
  之后即可在网页「变更验收 → 新建验证」中填入:
    仓库路径   demo/spring-backend (绝对路径见脚本输出)
    基准版本   base
    待检查版本 head-v1
    需求文件   demo/requirement.txt
  提交后 SpecProof 会真实执行检查, 预期发现「未认证用户可修改邮箱」的
  回归 (BLOCKED 判定)。

  幂等: 已存在 git 引用时直接输出使用说明, 不会重复创建。

.EXAMPLE
  pwsh scripts/prepare_demo_repo.ps1
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$DemoDir  = Join-Path $RepoRoot "demo\spring-backend"
$SpecPath = Join-Path $RepoRoot "demo\requirement.txt"
$Controller = Join-Path $DemoDir "src\main\java\com\specproof\demo\controller\UserController.java"

if (-not (Test-Path -LiteralPath $DemoDir)) {
    Write-Host "未找到演示仓库目录: $DemoDir" -ForegroundColor Red
    exit 1
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "未找到 git 命令, 请先安装 Git 并加入 PATH。" -ForegroundColor Red
    exit 1
}

function Show-Usage {
    Write-Host ""
    Write-Host "演示仓库已就绪:" -ForegroundColor Green
    Write-Host "  仓库路径   : $DemoDir"
    Write-Host "  基准版本   : base          (权限检查完整)"
    Write-Host "  待检查版本 : head-v1   (移除了 @PreAuthorize 权限检查)"
    Write-Host "  需求文件   : $SpecPath"
    Write-Host ""
    Write-Host "在网页 变更验收 -> 新建验证 中填入以上四项, 提交后等待执行完成," -ForegroundColor Cyan
    Write-Host "预期结论为 BLOCKED — 发现「未认证用户可修改邮箱」的回归与证据。" -ForegroundColor Cyan
    Write-Host ""
}

# ── 幂等: 两个引用都存在则直接使用 ──
if (Test-Path -LiteralPath (Join-Path $DemoDir ".git")) {
    git -C $DemoDir rev-parse --verify --quiet base *> $null
    $baseOk = ($LASTEXITCODE -eq 0)
    git -C $DemoDir rev-parse --verify --quiet head-v1 *> $null
    $headOk = ($LASTEXITCODE -eq 0)
    if ($baseOk -and $headOk) {
        Write-Host "演示仓库已初始化 (base / head-v1 均存在), 无需重复执行。" -ForegroundColor DarkGray
        Show-Usage
        exit 0
    }
}

Write-Host "==> 初始化演示仓库 git 历史 ..." -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath (Join-Path $DemoDir ".git"))) {
    git -C $DemoDir init -q
}

# 演示提交需要一个固定身份, 仅写入本仓库配置
git -C $DemoDir config user.name "SpecProof Demo"
git -C $DemoDir config user.email "demo@specproof.local"

# ── base: 原始实现 ──
git -C $DemoDir add -A
if ($LASTEXITCODE -ne 0) { Write-Host "git add 失败" -ForegroundColor Red; exit 1 }
# 有变更才提交, 避免空提交报错
git -C $DemoDir diff --cached --quiet *> $null
if ($LASTEXITCODE -ne 0) {
    git -C $DemoDir commit -q -m "demo: 原始实现 (权限检查完整)"
}
git -C $DemoDir tag -f base | Out-Null

# ── head-v1: 移除 @PreAuthorize 权限检查 ──
$content = Get-Content -LiteralPath $Controller -Raw -Encoding UTF8
if ($content -notmatch '@PreAuthorize\("isAuthenticated\(\)"\)') {
    Write-Host "权限检查注解已不在源文件中, 无法构造演示改动。" -ForegroundColor Yellow
    Write-Host "如想重置演示仓库, 删除 $DemoDir\.git 并还原文件后重跑本脚本。" -ForegroundColor Yellow
    exit 1
}
$mutated = $content -replace '\s*@PreAuthorize\("isAuthenticated\(\)"\)\r?\n', "`r`n"
[System.IO.File]::WriteAllText($Controller, $mutated, (New-Object System.Text.UTF8Encoding($false)))

try {
    git -C $DemoDir add -A
    git -C $DemoDir diff --cached --quiet *> $null
    if ($LASTEXITCODE -ne 0) {
        git -C $DemoDir commit -q -m "demo: 移除邮箱修改接口的权限检查 (演示回归)"
    }
    git -C $DemoDir tag -f head-v1 | Out-Null
} finally {
    # 恢复工作区到 base 的原始内容, 避免污染用户的演示副本
    git -C $DemoDir checkout -q -- .
    git -C $DemoDir checkout -q base 2>$null
}

Write-Host "    [ok] base -> head-v1 演示提交完成" -ForegroundColor Green

Show-Usage
exit 0
