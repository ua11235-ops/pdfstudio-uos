# 推送到 GitHub 的辅助脚本（本地用，不入库）
#
# 用法（PowerShell）：
#   $env:GH_TOKEN = "ghp_xxx"
#   .\packaging\push_to_github.ps1
#
# 它会：
#   1. 用 token 调 GitHub API 建一个私有仓库 pdfstudio-uos（已存在则跳过）
#   2. 把 origin 指到该仓库
#   3. 推送 main 分支
#   4. 打 tag v1.0.0 并推送
#
# token 需要权限：classic 勾 repo；fine-grained 需要
#   Administration: Read and write（建仓库）+ Contents: Read and write（推代码）
#
# 注意：token 只从环境变量读，不写进 git config、不进 URL、不进远程地址，
# 推完就失效（用户自己去 GitHub 删除）。这样即使仓库被别人看到也没有凭证残留。

param(
    [string]$Owner = "",
    [string]$Repo = "pdfstudio-uos",
    [string]$Tag = "v1.0.0",
    [switch]$SkipTag
)

$ErrorActionPreference = "Stop"

$token = $env:GH_TOKEN
if (-not $token) {
    Write-Host "!! 没有设置 GH_TOKEN" -ForegroundColor Red
    Write-Host "   先执行：`$env:GH_TOKEN = \"ghp_你的token\""
    exit 1
}

$git = "git"
if (-not (Get-Command $git -ErrorAction SilentlyContinue)) {
    $candidate = "C:\Program Files\Git\cmd\git.exe"
    if (Test-Path $candidate) { $git = $candidate } else {
        Write-Host "!! 找不到 git，先装 Git for Windows" -ForegroundColor Red
        exit 1
    }
}

$headers = @{
    Authorization          = "Bearer $token"
    Accept                 = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
    "User-Agent"           = "pdfstudio-push-script"
}

# ---- 1. 确认身份 ----
Write-Host "==> 校验 token"
$me = Invoke-RestMethod -Uri "https://api.github.com/user" -Headers $headers -Method Get
if (-not $Owner) { $Owner = $me.login }
Write-Host "    已登录：$($me.login)"

# ---- 2. 建仓库（已存在就复用） ----
$repoUrl = "https://api.github.com/repos/$Owner/$Repo"
$exists = $true
try {
    Invoke-RestMethod -Uri $repoUrl -Headers $headers -Method Get | Out-Null
    Write-Host "    仓库已存在：$Owner/$Repo"
} catch {
    $exists = $false
}

if (-not $exists) {
    Write-Host "==> 创建私有仓库 $Owner/$Repo"
    $body = @{
        name        = $Repo
        private     = $true
        description = "PDF 工作台：面向统信 UOS / Deepin / 麒麟 与 Windows 的轻量 PDF 编辑器"
        has_issues  = $true
        has_wiki    = $false
    } | ConvertTo-Json
    $req = @{
        Uri         = "https://api.github.com/user/repos"
        Headers     = $headers
        Method      = "Post"
        Body        = $body
        ContentType = "application/json"
    }
    Invoke-RestMethod @req | Out-Null
    Write-Host "    已创建"
}

# ---- 3. 配置远程并推送 ----
Write-Host "==> 推送 main"
$remote = "https://github.com/$Owner/$Repo.git"
$authUrl = "https://x-access-token:$token@github.com/$Owner/$Repo.git"

# token 只放在这一次推送的 URL 里（credential.helper 置空，避免被存进凭据管理器）
& $git remote remove origin 2>$null
& $git remote add origin $remote
& $git -c credential.helper= push $authUrl "refs/heads/main:refs/heads/main" --force
if ($LASTEXITCODE -ne 0) {
    Write-Host "!! 推送失败" -ForegroundColor Red
    exit 1
}

# ---- 4. 打 tag ----
if (-not $SkipTag) {
    Write-Host "==> 打标签 $Tag"
    & $git tag -f $Tag
    & $git -c credential.helper= push $authUrl "refs/tags/$Tag:refs/tags/$Tag" --force
}

Write-Host ""
Write-Host "完成：https://github.com/$Owner/$Repo" -ForegroundColor Green
Write-Host "提醒：这个 token 已经出现在你的终端历史里，用完请到 GitHub 设置里删除。"
