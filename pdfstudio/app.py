# -*- coding: utf-8 -*-
"""程序入口：初始化 Qt、应用主题、打开命令行传入的文件。"""

import os
import sys
import traceback

from . import APP_NAME, APP_NAME_CN, APP_ID, __version__
from .qtcompat import QtCore, QtGui, QtWidgets, qexec, high_dpi_setup

from .ui import icons, theme
from .ui.main_window import MainWindow


def _install_excepthook(app):
    """未捕获异常时弹窗提示，而不是让窗口直接消失。"""

    def handler(exc_type, exc_value, exc_tb):
        message = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        sys.stderr.write(message)
        try:
            box = QtWidgets.QMessageBox()
            box.setIcon(QtWidgets.QMessageBox.Critical)
            box.setWindowTitle("%s 出现异常" % APP_NAME_CN)
            box.setText("程序遇到了一个错误，当前操作可能没有完成。")
            box.setInformativeText(str(exc_value)[:500])
            box.setDetailedText(message)
            box.exec()
        except Exception:
            pass

    sys.excepthook = handler


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv)

    high_dpi_setup()
    app = QtWidgets.QApplication(argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_NAME_CN)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("PDF Studio")
    app.setDesktopFileName("pdfstudio")
    app.setWindowIcon(QtGui.QIcon(icons.app_icon(256)))

    theme.apply(app)
    _install_excepthook(app)

    target = None
    for arg in argv[1:]:
        if arg.lower().endswith(".pdf") and os.path.isfile(arg):
            target = arg
            break

    window = MainWindow(target)
    window.show()
    return qexec(app)


if __name__ == "__main__":
    sys.exit(main())
