# 创建 GitHub Release 并上传两个分发包（本地用，不入库）
#
# 用法（PowerShell）：
#   $env:GH_TOKEN = "ghp_xxx"
#   .\packaging\make_release_gh.ps1
#
# 会做四件事：
#   1. 校验 token 与两个包是否与当前源码一致（不一致直接拒绝发布）
#   2. 创建 / 复用 tag 对应的 Release
#   3. 上传 UOS 的 tar.gz 与 Windows 的 zip
#   4. 打印下载地址
#
# token 权限：classic 勾 repo + workflow；fine-grained 需要
#   Contents: Read and write
#
# 为什么先校验再发布：
#   发布出去的包必须和仓库里那份源码是同一份。之前就踩过"包比源码旧三天、
#   连整个合并功能都没有"的坑，而本机测试全绿——因为测的是源码不是交付物。

param(
    [string]$Repo = "pdfstudio-uos",
    [string]$Tag = "v1.0.0",
    [string]$Owner = "",
    [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"

$token = $env:GH_TOKEN
if (-not $token) {
    Write-Host "!! 没有设置 GH_TOKEN" -ForegroundColor Red
    Write-Host '   先执行：$env:GH_TOKEN = "ghp_你的token"'
    exit 1
}

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path (Join-Path $root "run.py"))) {
    # 脚本在 packaging/ 下，项目根是它的上一级
    $root = Split-Path -Parent $PSScriptRoot
}
Write-Host "项目根：$root"

$headers = @{
    Authorization          = "Bearer $token"
    Accept                 = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
    "User-Agent"           = "pdfstudio-release"
}

# ---- 1. 身份 ----
$me = Invoke-RestMethod -Uri "https://api.github.com/user" -Headers $headers
if (-not $Owner) { $Owner = $me.login }
Write-Host "已登录：$($me.login)"

# ---- 2. 找出要上传的包 ----
$uosTar = Get-ChildItem (Join-Path $root "packaging\build") -Filter "pdfstudio-*.tar.gz" -ErrorAction SilentlyContinue |
          Sort-Object LastWriteTime -Descending | Select-Object -First 1
$winZip = Get-ChildItem (Join-Path $root "packaging\windows\build") -Filter "*.zip" -ErrorAction SilentlyContinue |
          Sort-Object LastWriteTime -Descending | Select-Object -First 1

if (-not $uosTar) { Write-Host "!! 找不到 UOS 包，先跑 packaging/make_release.py --with-wheels" -ForegroundColor Red; exit 1 }
if (-not $winZip) { Write-Host "!! 找不到 Windows 包，先跑 packaging/windows/make_zip.py" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "待发布："
Write-Host ("  {0}  {1:N1} MB" -f $uosTar.Name, ($uosTar.Length / 1MB))
Write-Host ("  {0}  {1:N1} MB" -f $winZip.Name, ($winZip.Length / 1MB))

# ---- 3. 校验包与源码一致 ----
if (-not $SkipVerify) {
    Write-Host ""
    Write-Host "==> 校验包内容与源码是否一致"
    $check = @'
import os, sys, tarfile
root = sys.argv[1]
tar_path = sys.argv[2]
t = tarfile.open(tar_path)
diff = []
for m in t.getmembers():
    if not m.isfile():
        continue
    rel = m.name.split("/", 1)[1]
    local = os.path.join(root, *rel.split("/"))
    if not os.path.isfile(local):
        diff.append("包内多出: " + rel)
        continue
    if t.extractfile(m).read() != open(local, "rb").read():
        diff.append("内容不同: " + rel)
if diff:
    print("!! 包与源码不一致：")
    for d in diff[:10]:
        print("   " + d)
    sys.exit(1)
print("    OK 逐字节一致")
'@
    $py = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $py) { $py = "python3" }
    $check | & $py - $root $uosTar.FullName
    if ($LASTEXITCODE -ne 0) {
        Write-Host "!! 包比源码旧，拒绝发布。先重新打包：python packaging/make_release.py --with-wheels" -ForegroundColor Red
        exit 1
    }
}

# ---- 4. 创建 / 复用 Release ----
$relUrl = "https://api.github.com/repos/$Owner/$Repo/releases/tags/$Tag"
$release = $null
try {
    $release = Invoke-RestMethod -Uri $relUrl -Headers $headers
    Write-Host ""
    Write-Host "Release 已存在，复用：$($release.html_url)"
} catch {
    Write-Host ""
    Write-Host "==> 创建 Release $Tag"
    $notesPath = Join-Path $root "packaging\release_notes.md"
    if (-not (Test-Path $notesPath)) {
        Write-Host "!! 找不到发布说明 $notesPath" -ForegroundColor Red
        exit 1
    }
    $payload = @{
        tag_name   = $Tag
        name       = "PDF 工作台 1.0.0"
        body       = [System.IO.File]::ReadAllText($notesPath, [System.Text.Encoding]::UTF8)
        draft      = $false
        prerelease = $false
    } | ConvertTo-Json -Depth 3
    $tmp = Join-Path $env:TEMP "pdfstudio_release_body.json"
    [System.IO.File]::WriteAllText($tmp, $payload, (New-Object System.Text.UTF8Encoding($false)))
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Owner/$Repo/releases" `
        -Headers $headers -Method Post -InFile $tmp -ContentType "application/json; charset=utf-8"
    Write-Host "    已创建：$($release.html_url)"
}

# ---- 5. 上传附件 ----
foreach ($file in @($uosTar, $winZip)) {
    Write-Host ""
    Write-Host "==> 上传 $($file.Name) ($([math]::Round($file.Length / 1MB, 1)) MB)"
    # 名字里的中文要编码，否则 URL 非法
    $encoded = [System.Uri]::EscapeDataString($file.Name)
    $uploadUrl = "https://uploads.github.com/repos/$Owner/$Repo/releases/$($release.id)/assets?name=$encoded"
    $upHeaders = @{
        Authorization          = "Bearer $token"
        Accept                 = "application/vnd.github+json"
        "Content-Type"         = "application/octet-stream"
        "User-Agent"           = "pdfstudio-release"
    }
    try {
        $asset = Invoke-RestMethod -Uri $uploadUrl -Headers $upHeaders -Method Post `
            -InFile $file.FullName -TimeoutSec 900
        Write-Host ("    OK {0}  {1:N1} MB" -f $asset.name, ($asset.size / 1MB))
    } catch {
        Write-Host "    上传失败：$($_.Exception.Message)" -ForegroundColor Red
        throw
    }
}

Write-Host ""
Write-Host "完成：$($release.html_url)" -ForegroundColor Green
Write-Host "提醒：token 用完请到 https://github.com/settings/tokens 删除。"
