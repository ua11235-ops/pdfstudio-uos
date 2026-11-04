# -*- coding: utf-8 -*-
"""Qt 兼容层。

统信 UOS / Deepin 的软件仓库里默认提供的是 **PyQt5**（python3-pyqt5），
而较新的发行版 / pip 环境里更常见 **PySide6**。本文件把两者的差异收敛到一处，
其余代码只 import 本模块，从而做到"装哪个都能跑"。
"""

import os

QT_API = ""

try:  # 优先 PySide6（Qt6）
    from PySide6 import QtCore, QtGui, QtWidgets, QtSvg  # noqa: F401
    from PySide6.QtPrintSupport import QPrinter, QPrintDialog  # noqa: F401

    QT_API = "PySide6"
except ImportError:  # 退回 PyQt5（UOS 仓库默认版本）
    from PyQt5 import QtCore, QtGui, QtWidgets, QtSvg  # noqa: F401
    from PyQt5.QtPrintSupport import QPrinter, QPrintDialog  # noqa: F401

    QT_API = "PyQt5"

Qt = QtCore.Qt

# 信号 / 槽：PySide 是 Signal/Slot，PyQt 是 pyqtSignal/pyqtSlot
Signal = getattr(QtCore, "Signal", None) or QtCore.pyqtSignal
Slot = getattr(QtCore, "Slot", None) or QtCore.pyqtSlot

# QAction / QShortcut：Qt6 移到 QtGui，Qt5 在 QtWidgets
QAction = getattr(QtGui, "QAction", None) or QtWidgets.QAction
QActionGroup = getattr(QtGui, "QActionGroup", None) or QtWidgets.QActionGroup
QShortcut = getattr(QtGui, "QShortcut", None) or QtWidgets.QShortcut

# QImage 的像素格式枚举在 Qt5 / Qt6 下取值方式不同
def image_format(name):
    fmt = getattr(QtGui.QImage, "Format_" + name, None)
    if fmt is None:
        fmt = getattr(QtGui.QImage.Format, name)
    return fmt


RGB888 = image_format("RGB888")


def qexec(obj):
    """QApplication / QDialog 的 exec：Qt5 叫 exec_，Qt6 叫 exec。"""
    fn = getattr(obj, "exec", None)
    if fn is None:
        fn = getattr(obj, "exec_")
    return fn()


def high_dpi_setup():
    """高分屏支持。Qt6 默认已开启，Qt5 需要手动打开。"""
    if QT_API == "PyQt5":
        try:
            QtCore.QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
            QtCore.QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        except Exception:
            pass


def desktop_dir():
    """UOS 桌面目录（用于"导出到桌面"之类的默认路径）。"""
    home = os.path.expanduser("~")
    for name in ("Desktop", u"桌面"):
        candidate = os.path.join(home, name)
        if os.path.isdir(candidate):
            return candidate
    return home
