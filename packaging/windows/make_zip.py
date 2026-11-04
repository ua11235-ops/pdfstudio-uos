# -*- coding: utf-8 -*-
"""把打包好的程序 + 安装脚本打成一个分发包。

    python packaging/windows/make_zip.py

产物：packaging/windows/build/PDF工作台-1.0.0-Windows.zip

包里是"解压 → 双击 安装.bat"就能用的结构，不需要管理员权限。
"""

import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
VERSION = "1.0.0"
NAME = u"PDF工作台-%s-Windows" % VERSION

# 找打包产物：自动挑最新那次构建。
# 不写死 dist3 —— PyInstaller 重建时如果旧目录删不掉（沙箱、文件占用），
# 就会换个 dist4、dist5 继续，写死名字等于打包出一个星期前的旧程序。
APP_DIR = None
_dists = []
for entry in sorted(os.listdir(HERE)):
    full = os.path.join(HERE, entry)
    if not entry.startswith("dist") or not os.path.isdir(full):
        continue
    app = os.path.join(full, "PDFStudio")
    if os.path.isfile(os.path.join(app, "PDFStudio.exe")):
        _dists.append((os.path.getmtime(app), app))
if _dists:
    _dists.sort(reverse=True)
    APP_DIR = _dists[0][1]
if APP_DIR is None:
    sys.exit("找不到打包产物，请先运行 PyInstaller（见 pdfstudio.spec）")
print("==> 使用构建产物：%s" % os.path.basename(os.path.dirname(APP_DIR)))

# 需要一起放进压缩包的安装文件
FILES = [
    u"安装.bat", u"卸载.bat", "install.ps1", "uninstall.ps1", u"使用说明.txt",
]

out_dir = os.path.join(HERE, "build")
if not os.path.isdir(out_dir):
    os.makedirs(out_dir)
out_zip = os.path.join(out_dir, NAME + ".zip")

# 打包前强制过一遍编码/换行。这一步不能靠"记得手动跑"：
# .bat 一旦是 LF 换行，cmd 会按错误偏移解析（setlocal → etlocal），
# 用户那边双击直接失败，而我们在本机用 bash 跑又看不出来。
print("==> 规范化脚本编码与换行")
sys.path.insert(0, HERE)
import _fix_scripts
_fix_scripts.main()

print("")
print("==> 检查安装文件")
for name in FILES:
    path = os.path.join(HERE, name)
    if not os.path.isfile(path):
        sys.exit("缺少文件：%s" % name)

print("==> 压缩（约 160MB，需要一会儿）")
count = 0
with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for name in FILES:
        zf.write(os.path.join(HERE, name), NAME + "/" + name)
    base = APP_DIR
    for folder, _dirs, files in os.walk(base):
        for fname in files:
            full = os.path.join(folder, fname)
            rel = os.path.relpath(full, base).replace("\\", "/")
            zf.write(full, NAME + "/PDFStudio/" + rel)
            count += 1

size = os.path.getsize(out_zip) / 1024.0 / 1024.0
print("")
print("    ✓ 生成：%s" % out_zip)
print("    ✓ %.1f MB，程序文件 %d 个" % (size, count))
print("")
print("  发给同事后：解压 → 双击「安装.bat」→ 完成")
print("")
