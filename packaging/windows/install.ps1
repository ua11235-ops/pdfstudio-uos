# PDF 工作台 —— 安装脚本（当前用户，无需管理员权限）
#
# 做四件事：
#   1. 把程序拷到 %LOCALAPPDATA%\Programs\PDFStudio
#   2. 建开始菜单 + 桌面快捷方式
#   3. 注册 .pdf 文件关联（先备份你原来的关联，卸载时还原）
#   4. 在"应用和功能"里登记卸载入口
#
# 参数：
#   -NoAssociate   只装程序，不动 .pdf 关联
#   -NoDesktop     不建桌面快捷方式
#   -DryRun        只打印要做的事，不实际改动
#   -AppDir <路径>  手动指定 PDFStudio 程序目录（目录结构不标准时用）

param(
    [switch]$NoAssociate,
    [switch]$NoDesktop,
    [switch]$DryRun,
    [string]$AppDir = ""
)

$ErrorActionPreference = "Stop"

$AppName    = "PDF 工作台"
$AppId      = "PDFStudio"
$ExeName    = "PDFStudio.exe"
$ProgId     = "PDFStudio.Document"
$Version    = "1.0.0"

$SourceDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\PDFStudio"
$ExePath    = Join-Path $InstallDir $ExeName

function Info($text) { Write-Host "  $text" }
function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Warn($text) { Write-Host "  ! $text" -ForegroundColor Yellow }
function Ok($text)   { Write-Host "  OK $text" -ForegroundColor Green }

function Find-AppSource($base, $hint) {
    # 用户手动指定的优先，指错了就直接失败，不去猜
    if ($hint) {
        $resolved = Resolve-Path -LiteralPath $hint -ErrorAction SilentlyContinue
        if ($resolved -and (Test-Path (Join-Path $resolved.Path $ExeName))) {
            return $resolved.Path
        }
        return $null
    }

    # 标准布局：脚本旁边的 PDFStudio\
    $direct = Join-Path $base "PDFStudio"
    if (Test-Path (Join-Path $direct $ExeName)) { return $direct }

    # 兜底：有人会多套一层目录（先解压到 X，又把整个 X 拖进别的文件夹），
    # 或者把 PDFStudio 里的东西直接摊在子目录里。多找一层能省掉一轮来回。
    $children = @(Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        $nested = Join-Path $child.FullName "PDFStudio"
        if (Test-Path (Join-Path $nested $ExeName)) { return $nested }
        if (Test-Path (Join-Path $child.FullName $ExeName)) { return $child.FullName }
    }

    # 最后一种：在源码目录里直接双击了本脚本。
    # 那里程序在 dist3/PDFStudio（PyInstaller 的输出目录），不叫 PDFStudio。
    # 不认这个的话，开发机上每次点 安装.bat 都报"找不到 PDFStudio.exe"，
    # 而这个报错看起来像打包坏了，很容易被当成真 bug 查半天。
    foreach ($devDir in @("dist3", "dist2", "dist")) {
        $devApp = Join-Path $base (Join-Path $devDir "PDFStudio")
        if (Test-Path (Join-Path $devApp $ExeName)) { return $devApp }
    }
    return $null
}

function Show-Layout($base) {
    Write-Host ""
    Write-Host "  —— 诊断信息 ——" -ForegroundColor Yellow
    Write-Host "    脚本所在目录：$base"
    $items = @(Get-ChildItem -LiteralPath $base -Force -ErrorAction SilentlyContinue)
    Write-Host ("    这个目录里共 {0} 项：" -f $items.Count)
    foreach ($i in $items) {
        if ($i.PSIsContainer) { $kind = "文件夹" } else { $kind = "文件  " }
        Write-Host ("      [{0}] {1}" -f $kind, $i.Name)
    }

    $appFolder = Join-Path $base "PDFStudio"
    Write-Host ""
    if (Test-Path $appFolder) {
        Write-Host "    有 PDFStudio 文件夹，但里面没有 $ExeName。" -ForegroundColor Yellow
        Write-Host "    里面现在是："
        Get-ChildItem -LiteralPath $appFolder -Force -ErrorAction SilentlyContinue |
            Select-Object -First 8 |
            ForEach-Object { Write-Host ("      " + $_.Name) }
        Write-Host ""
        Write-Host "    → 主程序被删掉了。最常见的原因是杀毒软件把它隔离了"
        Write-Host "      （PyInstaller 打的 exe 很容易被误判）。"
        Write-Host "      处理：把整个解压目录加进杀软的白名单，再重新解压一次 zip。"
    } else {
        Write-Host "    这个目录里没有 PDFStudio 文件夹。" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "    → 最常见的原因：直接在压缩包里双击了本文件。"
        Write-Host "      Windows 只会把被双击的那一个文件解压到临时目录，"
        Write-Host "      程序本体还在压缩包里，当然找不到。"
        Write-Host ""
        Write-Host "      正确做法：右键 zip 文件 → 全部解压"
        Write-Host "                → 进入解压出来的文件夹"
        Write-Host "                → 再双击 安装.bat"
    }

    Write-Host ""
    Write-Host "    如果程序确实在别的位置，可以手动指定：" -ForegroundColor Yellow
    Write-Host "      在这个文件夹的地址栏输入 cmd 回车，然后敲："
    Write-Host "      安装.bat -AppDir `"D:\某个路径\PDFStudio`""
    Write-Host ""
}

Write-Host ""
Write-Host "  $AppName $Version  安装程序" -ForegroundColor White
if ($DryRun) { Write-Host "  （预演模式：不会改动任何东西）" -ForegroundColor Yellow }

# ---------- 前置检查 ----------
$AppSource = Find-AppSource $SourceDir $AppDir
if (-not $AppSource) {
    Write-Host ""
    Write-Host "  找不到 $ExeName。" -ForegroundColor Red
    Write-Host "  请确认本脚本和 PDFStudio 文件夹在同一个目录里。" -ForegroundColor Red
    Show-Layout $SourceDir
    exit 1
}
if ($AppSource -ne (Join-Path $SourceDir "PDFStudio")) {
    Info "程序目录不在标准位置，已自动找到：$AppSource"
    if ($AppSource -match "\\dist\d?\\") {
        Warn "这是开发构建目录。正式分发请用 zip 解压后那个 安装.bat。"
    }
}

# 正在运行就先关掉，否则文件被占用会拷不进去
$running = Get-Process -Name "PDFStudio" -ErrorAction SilentlyContinue
if ($running) {
    Step "关闭正在运行的 $AppName"
    $running | ForEach-Object { $_.Kill() }
    Start-Sleep -Milliseconds 800
    Ok "已关闭"
}

# ---------- 拷贝程序 ----------
Step "安装到 $InstallDir"
if ($DryRun) {
    Info "（预演）会把 $AppSource 复制到 $InstallDir"
} else {
    if (Test-Path $InstallDir) {
        # 覆盖安装：清掉旧版本，避免残留旧文件
        Remove-Item -Path $InstallDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    Copy-Item -Path (Join-Path $AppSource "*") -Destination $InstallDir -Recurse -Force
    # 卸载脚本要放进安装目录：「应用和功能」里的卸载入口指向它，
    # 用户把解压出来的文件夹删了也能正常卸载。
    Copy-Item -Path (Join-Path $SourceDir "uninstall.ps1") -Destination $InstallDir -Force
    Copy-Item -Path (Join-Path $SourceDir "卸载.bat")      -Destination $InstallDir -Force
    Ok "程序文件已就位"
}

# ---------- 快捷方式 ----------
Step "创建快捷方式"
$shell = New-Object -ComObject WScript.Shell

$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$lnkStart  = Join-Path $startMenu "$AppName.lnk"
$lnkDesk   = Join-Path ([Environment]::GetFolderPath("Desktop")) "$AppName.lnk"

function New-Shortcut($path) {
    if ($DryRun) { Info "（预演）$path"; return }
    $sc = $shell.CreateShortcut($path)
    $sc.TargetPath       = $ExePath
    $sc.WorkingDirectory = $InstallDir
    $sc.IconLocation     = "$ExePath,0"
    $sc.Description      = "PDF 工作台 —— 查看与编辑 PDF"
    $sc.Save()
    Ok $path
}

New-Shortcut $lnkStart
if (-not $NoDesktop) { New-Shortcut $lnkDesk }

# ---------- 文件关联 ----------
if ($NoAssociate) {
    Step "跳过文件关联（-NoAssociate）"
} else {
    Step "注册 PDF 文件关联"

    # 先把你原来的 .pdf 关联记下来，卸载时好还原
    $extKey  = "HKCU:\Software\Classes\.pdf"
    $backup  = "HKCU:\Software\$AppId"
    $prevVal = ""
    if (Test-Path $extKey) {
        $item = Get-Item $extKey
        $prevVal = [string]$item.GetValue("")
    }

    if ($DryRun) {
        Info "（预演）.pdf 当前关联：$(if ($prevVal) { $prevVal } else { '（无）' })"
        Info "（预演）会改为 $ProgId"
    } else {
        # 备份：只记「别人」的关联。
        # 重复安装（覆盖安装）时 .pdf 已经是本程序的 ProgId，这时候绝不能覆盖备份，
        # 否则备份里存的就是自己的 ProgId，卸载时会把 .pdf 还原成一个刚被删掉的
        # ProgId，双击 PDF 直接变成"没有关联"——用户会以为卸载把系统搞坏了。
        #
        # 顺序很重要：必须先读再建。New-Item -Force 在注册表提供程序上不是"已存在就跳过"，
        # 而是把整个键重建一遍，原有的值全没了——备份会被自己清空。
        $hasBackup = $false
        if (Test-Path $backup) {
            $existing = Get-ItemProperty -Path $backup -ErrorAction SilentlyContinue
            if ($existing -and $existing.PSObject.Properties.Name -contains "PrevPdfProgId") {
                $hasBackup = $true
            }
        }
        if (-not (Test-Path $backup)) {
            New-Item -Path $backup -Force | Out-Null
        }

        if ($prevVal -ne $ProgId) {
            Set-ItemProperty -Path $backup -Name "PrevPdfProgId" -Value $prevVal
        } elseif (-not $hasBackup) {
            # 之前就是本程序，却没有任何备份记录（比如更早的版本装的），
            # 那就当成"装之前没有关联"，卸载时直接清掉键。
            Set-ItemProperty -Path $backup -Name "PrevPdfProgId" -Value ""
        }
        Set-ItemProperty -Path $backup -Name "InstallDir" -Value $InstallDir

        # ProgId：说明这是什么类型、用什么打开、用什么图标
        $progKey = "HKCU:\Software\Classes\$ProgId"
        New-Item -Path $progKey -Force | Out-Null
        Set-Item -Path $progKey -Value "PDF 文档"
        New-Item -Path "$progKey\DefaultIcon" -Force | Out-Null
        Set-Item -Path "$progKey\DefaultIcon" -Value "$ExePath,0"
        New-Item -Path "$progKey\shell\open\command" -Force | Out-Null
        Set-Item -Path "$progKey\shell\open\command" -Value "`"$ExePath`" `"%1`""

        # .pdf 指向我们的 ProgId。
        # 这里只写默认值，绝对不能 New-Item -Force——那会把整个 .pdf 键重建，
        # 把系统原本放在里面的 OpenWithProgids / PersistentHandler 等一起清掉，
        # 用户以后想换回原来的阅读器就找不到入口了。
        if (-not (Test-Path $extKey)) {
            New-Item -Path $extKey -Force | Out-Null
        }
        Set-Item -Path $extKey -Value $ProgId
        Ok ".pdf 已关联到 $AppName"

        # Windows 10/11 里如果用户手动设过"始终使用"，UserChoice 优先级更高，
        # 注册表改了也不会生效，得去设置里改。这里提前说清楚，免得用户以为没装上。
        $uc = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pdf\UserChoice"
        if (Test-Path $uc) {
            Warn "系统里存在你手动指定过的 PDF 打开方式（UserChoice），它会覆盖本程序。"
            Warn "如果双击 PDF 没有用本程序打开，请到："
            Warn "  设置 → 应用 → 默认应用 → 按文件类型选择默认应用 → .pdf → 选 PDF 工作台"
        }
    }
}

# ---------- 卸载入口 ----------
Step "登记到「应用和功能」"
$uninstKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppId"
if ($DryRun) {
    Info "（预演）$uninstKey"
} else {
    New-Item -Path $uninstKey -Force | Out-Null
    $size = 0
    if (Test-Path $InstallDir) {
        $size = [int](((Get-ChildItem $InstallDir -Recurse -File |
                        Measure-Object -Property Length -Sum).Sum) / 1KB)
    }
    Set-ItemProperty -Path $uninstKey -Name "DisplayName"     -Value $AppName
    Set-ItemProperty -Path $uninstKey -Name "DisplayVersion"  -Value $Version
    Set-ItemProperty -Path $uninstKey -Name "Publisher"       -Value "PDF Studio"
    Set-ItemProperty -Path $uninstKey -Name "DisplayIcon"     -Value "$ExePath,0"
    Set-ItemProperty -Path $uninstKey -Name "InstallLocation" -Value $InstallDir
    Set-ItemProperty -Path $uninstKey -Name "UninstallString" -Value "`"$InstallDir\卸载.bat`""
    Set-ItemProperty -Path $uninstKey -Name "NoModify" -Value 1 -Type DWord
    Set-ItemProperty -Path $uninstKey -Name "NoRepair" -Value 1 -Type DWord
    if ($size -gt 0) {
        Set-ItemProperty -Path $uninstKey -Name "EstimatedSize" -Value $size -Type DWord
    }
    Ok "已登记（可从 设置 → 应用 里卸载）"
}

# ---------- 通知资源管理器刷新图标 ----------
if (-not $DryRun) {
    try {
        Add-Type -Namespace Win32 -Name Shell -MemberDefinition @'
[DllImport("shell32.dll", CharSet = CharSet.Auto)]
public static extern void SHChangeNotify(int eventId, int flags, System.IntPtr item1, System.IntPtr item2);
'@
        [Win32.Shell]::SHChangeNotify(0x08000000, 0x0000, [IntPtr]::Zero, [IntPtr]::Zero)
    } catch { }
}

Write-Host ""
if ($DryRun) {
    Write-Host "  预演结束，没有做任何改动。" -ForegroundColor Yellow
} else {
    Write-Host "  安装完成！" -ForegroundColor Green
    Write-Host ""
    Write-Host "  从桌面或开始菜单打开「$AppName」，"
    Write-Host "  也可以直接双击任意 PDF 文件。"
}
Write-Host ""
