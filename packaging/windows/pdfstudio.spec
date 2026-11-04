# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（Windows）。

用法（在项目根目录）：
    python -m PyInstaller packaging/windows/pdfstudio.spec --noconfirm

产物：packaging/windows/dist/PDFStudio/PDFStudio.exe
     这是"单目录"模式——启动快、杀软误报少，但整个目录要一起拷走。
     不要改成单文件模式，PySide6 单文件每次启动都要解压到临时目录，慢好几秒。
"""

import os
import sys

# spec 执行时 __file__ 不可靠，用 SPECPATH（PyInstaller 注入）
ROOT = os.path.dirname(os.path.dirname(SPECPATH))
WINDOWS_DIR = os.path.join(ROOT, "packaging", "windows")

# 没用到的 Qt 模块全部剔掉，能把体积从 250MB 压到 100MB 出头。
# 注意别删 QtNetwork / QtPrintSupport / QtSvg：
#   QtNetwork 被 Qt 内部和 QSettings 间接用到，
#   QtPrintSupport 是打印功能，QtSvg 用于渲染 SVG 图标。
EXCLUDES = [
    "tkinter", "unittest", "pydoc", "doctest", "test", "lib2to3",
    # PIL 只有测试脚本在用，程序本身不依赖；PyMuPDF 的可选集成会把它带进来
    "PIL",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DRender",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel", "PySide6.QtWebSockets",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2", "PySide6.QtQml", "PySide6.QtQmlModels",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
    "PySide6.QtSerialPort", "PySide6.QtSerialBus", "PySide6.QtSensors",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtStateMachine",
    "PySide6.QtTest", "PySide6.QtSql", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech", "PySide6.QtHttpServer",
    "PySide6.QtDBus",
]

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        # 内置示例文档，方便第一次打开时有东西可看
        (os.path.join(ROOT, "samples", "sample.pdf"), "samples"),
        (os.path.join(ROOT, "LICENSE"), "."),
    ],
    hiddenimports=[
        "pymupdf",
        # 打印支持必须显式声明，否则打包后点打印会崩
        "PySide6.QtPrintSupport",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)


def _keep(entry):
    """剔掉体积大又用不到的东西。

    opengl32sw.dll 是 Qt 的软件 OpenGL 兜底实现（20MB）。
    本程序全部是 QWidget 光栅绘制，不走 OpenGL，留着纯属浪费。
    Qt 的翻译文件只保留简体中文——打印对话框这类 Qt 自带界面的按钮
    才会用到它，删掉的话会变成英文。
    """
    name = entry[0].replace("\\", "/").lower()
    if name.endswith("opengl32sw.dll"):
        return False
    if "/translations/" in name and not name.endswith(("_zh_cn.qm", "_zh_tw.qm")):
        return False
    return True


a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PDFStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX 压缩极易被杀软误报，坚决不开
    console=False,      # 双击不弹黑窗口
    disable_windowed_traceback=False,
    icon=os.path.join(WINDOWS_DIR, "app.ico"),
    version=os.path.join(WINDOWS_DIR, "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PDFStudio",
)
