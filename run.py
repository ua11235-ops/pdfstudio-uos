#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF Studio 启动脚本（不安装也能直接运行）。

    python3 run.py                 # 打开空窗口
    python3 run.py 文档.pdf         # 直接打开指定文件

依赖缺失时不抛 ImportError 堆栈，而是给出可直接复制的修复命令——
桌面启动器里看不到终端输出，只有把话说清楚用户才知道该怎么办。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

APP_NAME_CN = "PDF 工作台"


def _missing_deps():
    """返回缺失的依赖名称列表；全部就绪时返回空列表。"""
    missing = []

    # PyMuPDF 1.24 起推荐 import pymupdf，旧版本只有 import fitz
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        try:
            import fitz  # noqa: F401
        except ImportError:
            missing.append("PyMuPDF")

    try:
        from PyQt5 import QtWidgets  # noqa: F401
    except ImportError:
        try:
            from PySide6 import QtWidgets  # noqa: F401
        except ImportError:
            missing.append("PyQt5 或 PySide6")

    return missing


def _report_missing(missing):
    py = sys.executable or "python3"
    ver = "%d.%d" % sys.version_info[:2]
    # 新版 PyMuPDF 的轮子已经不支持 Python 3.7/3.8，需要锁版本
    if sys.version_info[:2] <= (3, 7):
        pdf_spec = "pymupdf<=1.22.5"
    elif sys.version_info[:2] == (3, 8):
        pdf_spec = "pymupdf<=1.23.26"
    else:
        pdf_spec = "pymupdf"

    lines = [
        "",
        "  无法启动 %s：缺少运行依赖 %s" % (APP_NAME_CN, "、".join(missing)),
        "",
        "  当前解释器：%s  (Python %s)" % (py, ver),
        "",
        "  请在终端执行下面任意一组命令后重试：",
        "",
        "    # 方式一：系统包（UOS / Deepin / Ubuntu 推荐）",
        "    sudo apt install python3-pyqt5 python3-pymupdf",
        "",
        "    # 方式二：用 pip 装到上面这个解释器",
        "    %s -m pip install PyQt5 %s" % (py, pdf_spec),
        "",
        "    # 方式三：系统 Python 被锁定时加参数",
        "    %s -m pip install --break-system-packages PyQt5 %s" % (py, pdf_spec),
        "",
        "  已经安装过安装包的话，直接重跑安装脚本即可自动补齐：",
        "    sudo ./install.sh",
        "",
        "  环境诊断：./install.sh --doctor",
        "",
    ]
    sys.stderr.write("\n".join(lines))

    # 从桌面图标启动时没有终端，stderr 看不见，能用 Qt 就弹个窗
    if "PyQt5 或 PySide6" not in missing:
        try:
            from PyQt5 import QtWidgets as _qw
        except ImportError:
            from PySide6 import QtWidgets as _qw
        try:
            app = _qw.QApplication.instance() or _qw.QApplication(sys.argv[:1])
            box = _qw.QMessageBox()
            box.setIcon(_qw.QMessageBox.Critical)
            box.setWindowTitle(APP_NAME_CN)
            box.setText("缺少运行依赖：%s" % "、".join(missing))
            box.setInformativeText(
                "在终端执行以下命令后重试：\n\n"
                "sudo apt install python3-pymupdf\n\n"
                "或\n\n"
                "%s -m pip install %s" % (py, pdf_spec)
            )
            box.setDetailedText("\n".join(lines))
            box.exec()
            del app
        except Exception:
            pass


def _selftest(out_path):
    """打包自检：不弹窗，跑一遍真实渲染并截图。

    打包成 exe 之后最容易出问题的是 Qt 插件和 PyMuPDF 的 DLL 有没有带上，
    光看"进程没退出"是看不出来的——窗口可能是一片空白。
    这里直接把窗口画出来存成图片，再用像素种类判断是不是真画出了东西。
    """
    import tempfile

    try:
        import pymupdf as fitz
    except ImportError:
        import fitz

    from pdfstudio.qtcompat import QtCore, QtGui, QtWidgets
    from pdfstudio.ui import theme
    from pdfstudio.ui.main_window import MainWindow

    pdf = os.path.join(tempfile.gettempdir(), "pdfstudio_selftest.pdf")
    src = fitz.open()
    page = src.new_page(width=595, height=842)
    page.insert_text((60, 80), "PDF Studio selftest", fontsize=24)
    page.insert_text((60, 130), u"中文渲染自检", fontsize=20, fontname="china-s")
    page.draw_rect(fitz.Rect(60, 180, 500, 320), color=(0.8, 0.2, 0.2), width=2)
    src.save(pdf)
    src.close()

    app = QtWidgets.QApplication(sys.argv[:1])
    theme.apply(app)
    win = MainWindow()
    win.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
    win.resize(1200, 820)
    win.show()
    win.open_path(pdf)
    for _ in range(60):
        app.processEvents()
    win.grab().save(out_path)

    image = QtGui.QImage(out_path)
    colors = set()
    for y in range(0, image.height(), 7):
        for x in range(0, image.width(), 7):
            colors.add(image.pixel(x, y))

    # 打包成窗口程序后没有控制台，sys.stdout / stderr 可能是 None，
    # 直接 write 会抛 AttributeError，所以输出要容错。
    def _say(text):
        stream = sys.stdout or sys.stderr
        if stream is not None:
            try:
                stream.write(text + "\n")
            except Exception:
                pass

    if image.isNull() or len(colors) < 20:
        _say("SELFTEST FAIL 截图内容异常（颜色种类 %d）" % len(colors))
        return 1

    # 合并窗口自检：PyInstaller 漏收集 merge_dialog 时，用户要等到点
    # 「合并 PDF 文件」那一刻才崩，而那时程序已经在别人电脑上了。
    # 这里把「打开窗口 → 加文件 → 拖拽 → 写出」整条链路跑一遍。
    merged = os.path.join(tempfile.gettempdir(), "pdfstudio_selftest_merge.pdf")
    try:
        from pdfstudio.ui.merge_dialog import MergeDialog

        dialog = MergeDialog(None)
        dialog.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
        dialog.resize(1000, 700)
        dialog.show()
        dialog.add_paths([pdf])
        # 分两次加同一个文件：一次多选里重复会被去重，但用户再点一次「添加」
        # 就是明确要合并两遍，这里也顺带验证这条路径
        dialog.add_paths([pdf])
        for _ in range(30):
            app.processEvents()
        if dialog.plan.total_pages != 2:
            _say("SELFTEST FAIL 合并窗口没加载出页面（%d 页）" % dialog.plan.total_pages)
            return 1

        # 把第 2 页拖到最前，确认页序表跟着变
        page_list = dialog.page_list
        if not page_list.apply_drop([1], 0):
            _say("SELFTEST FAIL 合并拖拽没生效（页序还是 %r）" % (dialog.plan.order,))
            return 1
        for _ in range(10):
            app.processEvents()
        if dialog.plan.order != [(1, 0), (0, 0)]:
            _say("SELFTEST FAIL 合并拖拽后页序不对：%r" % (dialog.plan.order,))
            return 1

        dialog.plan.build(merged)
        dialog.reject()
        if not os.path.isfile(merged) or os.path.getsize(merged) < 500:
            _say("SELFTEST FAIL 合并没有写出文件")
            return 1
    except Exception as exc:
        _say("SELFTEST FAIL 合并功能异常：%r" % (exc,))
        return 1

    del app

    # 打印链路自检：真的走一遍 QPrinter，输出成 PDF。
    # 光检查 Qt6PrintSupport.dll 在不在没用——插件缺失时要到用户点"打印"
    # 那一刻才暴露，那时候程序已经在别人电脑上了。
    print_pdf = os.path.join(tempfile.gettempdir(), "pdfstudio_selftest_print.pdf")
    try:
        from pdfstudio.qtcompat import QPrinter
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(print_pdf)
        painter = QtGui.QPainter()
        if not painter.begin(printer):
            _say("SELFTEST FAIL 打印链路无法初始化（QPrinter）")
            return 1
        painter.drawImage(QtCore.QRectF(0, 0, 200, 200), image)
        painter.end()
        if not os.path.isfile(print_pdf) or os.path.getsize(print_pdf) < 500:
            _say("SELFTEST FAIL 打印输出为空")
            return 1
    except Exception as exc:
        _say("SELFTEST FAIL 打印链路异常：%r" % (exc,))
        return 1

    _say("SELFTEST OK %s  %dx%d  %d 种颜色  打印链路正常"
         % (out_path, image.width(), image.height(), len(colors)))
    return 0


def main():
    if "--selftest" in sys.argv:
        index = sys.argv.index("--selftest")
        out = sys.argv[index + 1] if len(sys.argv) > index + 1 else "selftest.png"
        return _selftest(os.path.abspath(out))

    missing = _missing_deps()
    if missing:
        _report_missing(missing)
        return 1

    from pdfstudio.app import main as run_app

    return run_app()


if __name__ == "__main__":
    sys.exit(main())
