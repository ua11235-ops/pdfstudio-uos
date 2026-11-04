# PDF 工作台 —— 卸载脚本
#
# 会做：删快捷方式、删文件关联（并还原你原来的）、删「应用和功能」里的登记、删程序目录。
# 不会动：你的 PDF 文件本身。

$ErrorActionPreference = "Stop"

$AppName    = "PDF 工作台"
$AppId      = "PDFStudio"
$ProgId     = "PDFStudio.Document"
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\PDFStudio"
$BackupKey  = "HKCU:\Software\$AppId"

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Ok($text)   { Write-Host "  OK $text" -ForegroundColor Green }
function Warn($text) { Write-Host "  ! $text" -ForegroundColor Yellow }

# 单项删不掉（被占用、权限、安全软件拦截）不能把整个卸载流程打断，
# 否则用户会遇到"卸载到一半停住、还剩一堆东西"。记下来最后统一提示。
$script:failed = @()
function Try-Remove($path, $what) {
    if (-not (Test-Path -LiteralPath $path)) { return }
    try {
        Remove-Item -LiteralPath $path -Force -ErrorAction Stop
        Ok $what
    } catch {
        $script:failed += $what
        Warn "$what 删除失败（可以手动删）：$path"
    }
}

Write-Host ""
Write-Host "  卸载 $AppName" -ForegroundColor White

$running = Get-Process -Name "PDFStudio" -ErrorAction SilentlyContinue
if ($running) {
    Step "关闭正在运行的 $AppName"
    $running | ForEach-Object { $_.Kill() }
    Start-Sleep -Milliseconds 800
    Ok "已关闭"
}

# ---------- 快捷方式 ----------
Step "删除快捷方式"
Try-Remove (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$AppName.lnk") "开始菜单快捷方式"
Try-Remove (Join-Path ([Environment]::GetFolderPath("Desktop")) "$AppName.lnk") "桌面快捷方式"

# ---------- 文件关联 ----------
Step "还原文件关联"
$extKey = "HKCU:\Software\Classes\.pdf"
$prev = ""
if (Test-Path $BackupKey) {
    $prev = [string](Get-ItemProperty -Path $BackupKey -Name "PrevPdfProgId" -ErrorAction SilentlyContinue).PrevPdfProgId
}

$current = ""
if (Test-Path $extKey) {
    $current = [string](Get-Item $extKey).GetValue("")
}

if ($current -eq $ProgId) {
    if ($prev) {
        # 装之前你就有别的关联，还原回去
        Set-Item -Path $extKey -Value $prev
        Ok ".pdf 已还原为 $prev"
    } else {
        # 装之前 .pdf 没有默认关联。只清默认值，不整键删除——
        # 这个键里可能还放着系统写的 OpenWithProgids / PersistentHandler，
        # 删了会让"打开方式"列表少掉东西，用户以为卸载把系统弄坏了。
        $k = Get-Item $extKey
        if ($k.SubKeyCount -eq 0 -and $k.ValueCount -le 1) {
            Remove-Item -Path $extKey -Force
            Ok ".pdf 关联已移除"
        } else {
            Set-Item -Path $extKey -Value ""
            Ok ".pdf 默认关联已清空"
        }
    }
} elseif ($current) {
    # 用户后来自己改过，别动它
    Warn ".pdf 现在指向 $current，不是本程序，保持不动"
}

Remove-Item -Path "HKCU:\Software\Classes\$ProgId" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path $BackupKey -Recurse -Force -ErrorAction SilentlyContinue

# ---------- 应用和功能登记 ----------
Step "移除「应用和功能」中的登记"
Remove-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppId" `
            -Recurse -Force -ErrorAction SilentlyContinue
Ok "已移除"

# 注意运算符优先级：-not 先结合，写成 `-not $current -eq $ProgId` 会变成
# (-not $current) -eq $ProgId，逻辑整个反过来，图标永远不刷新。
if ($current -ne $ProgId) {
    try {
        Add-Type -Namespace Win32 -Name Shell -MemberDefinition @'
[DllImport("shell32.dll", CharSet = CharSet.Auto)]
public static extern void SHChangeNotify(int eventId, int flags, System.IntPtr item1, System.IntPtr item2);
'@
        [Win32.Shell]::SHChangeNotify(0x08000000, 0x0000, [IntPtr]::Zero, [IntPtr]::Zero)
    } catch { }
}

# ---------- 删程序目录 ----------
Step "删除程序文件"
# 本脚本自己就在这个目录里，删不掉自己，所以分两步：
#   1. 先把除本脚本和 卸载.bat 之外的东西全删掉（这一步能立刻看到效果）
#   2. 剩下的空目录交给一个后台 cmd，等两秒我们退出之后再删
# 只做第 2 步的话，万一后台进程没起来，用户会剩下一整个 120MB 的目录。
if (Test-Path $InstallDir) {
    $keep = @(
        (Join-Path $InstallDir "uninstall.ps1"),
        (Join-Path $InstallDir "卸载.bat")
    )
    $left = 0
    Get-ChildItem -LiteralPath $InstallDir -Force | ForEach-Object {
        if ($keep -contains $_.FullName) { return }
        try {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction Stop
        } catch {
            $left += 1
        }
    }
    if ($left -gt 0) {
        $script:failed += "程序目录里有 $left 项没删掉"
    }

    $cmd = "timeout /t 2 >nul & rd /s /q `"$InstallDir`""
    try {
        Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $cmd -WindowStyle Hidden
        Ok "$InstallDir（后台清理中）"
    } catch {
        Warn "无法启动后台清理，请手动删除：$InstallDir"
    }
}

Write-Host ""
if ($script:failed.Count -gt 0) {
    Write-Host "  卸载完成，但有 $($script:failed.Count) 项没能自动删除：" -ForegroundColor Yellow
    foreach ($item in $script:failed) { Write-Host "    · $item" -ForegroundColor Yellow }
    Write-Host "  这些可以手动删，不影响其他部分已经清理干净。" -ForegroundColor Yellow
} else {
    Write-Host "  卸载完成。" -ForegroundColor Green
}
Write-Host ""
