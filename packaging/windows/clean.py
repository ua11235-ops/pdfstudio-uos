# -*- coding: utf-8 -*-
"""清理 Windows 打包的中间产物，只保留最终那一份。

PyInstaller 每次构建都会生成 dist*/build*，几轮下来好几个 G。
这个脚本按"保留指定目录，其余删除"的方式收拾干净。

    python packaging/windows/clean.py            # 保留最新构建
    python packaging/windows/clean.py --all      # 全清（连产物一起）
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _dists():
    """所有含完整程序的 dist* 目录，按新旧排序。"""
    found = []
    for entry in os.listdir(HERE):
        full = os.path.join(HERE, entry)
        if not entry.startswith("dist") or not os.path.isdir(full):
            continue
        app = os.path.join(full, "PDFStudio")
        if os.path.isfile(os.path.join(app, "PDFStudio.exe")):
            found.append((os.path.getmtime(app), entry))
    found.sort(reverse=True)
    return found


_available = _dists()
KEEP = None if "--all" in sys.argv else (_available[0][1] if _available else None)
# 目录名不写死：构建失败重试时会出现 dist4、build4，写死就清不掉
TARGETS = sorted(
    entry for entry in os.listdir(HERE)
    if (entry.startswith("dist") or entry.startswith("build") or entry == "_stage")
    and os.path.isdir(os.path.join(HERE, entry))
)

removed = []
for name in TARGETS:
    if KEEP and name == KEEP:
        continue
    path = os.path.join(HERE, name)
    if not os.path.isdir(path):
        continue
    size = 0
    for folder, _dirs, files in os.walk(path):
        for fname in files:
            try:
                size += os.path.getsize(os.path.join(folder, fname))
            except OSError:
                pass
    shutil.rmtree(path)
    removed.append((name, size / 1024.0 / 1024.0))

if not removed:
    print("没有需要清理的目录")
else:
    for name, size in removed:
        print("  已删除 %-8s %.0f MB" % (name, size))
    print("  共释放 %.0f MB" % sum(s for _n, s in removed))

if KEEP:
    final = os.path.join(HERE, KEEP, "PDFStudio")
    if os.path.isdir(final):
        total = 0
        for folder, _dirs, files in os.walk(final):
            for fname in files:
                total += os.path.getsize(os.path.join(folder, fname))
        print("  保留 %s（%.0f MB）" % (KEEP, total / 1024.0 / 1024.0))
