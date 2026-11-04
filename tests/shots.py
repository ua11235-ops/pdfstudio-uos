# -*- coding: utf-8 -*-
"""生成文档用的成品截图。"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

import pymupdf as fitz  # noqa: E402

from pdfstudio.qtcompat import QtCore, QtWidgets  # noqa: E402
from pdfstudio.core import annotate as ann  # noqa: E402
from pdfstudio.ui import theme  # noqa: E402
from pdfstudio.ui.main_window import MainWindow  # noqa: E402

OUT = os.path.join(ROOT, "screenshots")
os.makedirs(OUT, exist_ok=True)
SAMPLE = os.path.join(ROOT, "samples", "sample.pdf")


def pump(app, ms=200):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def decorate(win):
    doc = win.doc
    doc.begin_change("演示标注")
    page = doc.doc[0]
    ann.add_markup(page, "highlight", fitz.Rect(70, 118, 430, 142), (1.0, 0.86, 0.24), 0.55)
    ann.add_markup(page, "underline", fitz.Rect(70, 148, 430, 168), (0.32, 0.62, 1.0), 1.0)
    ann.add_markup(page, "strikeout", fitz.Rect(70, 248, 430, 268), (0.98, 0.35, 0.35), 1.0)
    ann.add_ink(page, [[(452, 236), (470, 258), (505, 208)]], (0.95, 0.35, 0.35), 2.6)
    ann.add_arrow(page, (476, 330), (434, 330), (0.25, 0.25, 0.28), 2.0)
    ann.add_textbox(page, fitz.Rect(70, 636, 430, 706),
                    "这段需要再确认一下，\n周五前给我反馈。", 12, (0.1, 0.1, 0.1),
                    (1.0, 0.97, 0.86), (0.94, 0.74, 0.20))
    ann.add_note(page, (540, 640), "第三行的数据来源待核实")
    doc.end_change()


def main():
    app = QtWidgets.QApplication(sys.argv)
    theme.apply(app)

    win = MainWindow()
    win.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
    win.resize(1440, 900)
    win.show()
    pump(app, 400)
    win.grab().save(os.path.join(OUT, "welcome.png"))

    win.open_path(SAMPLE)
    pump(app, 1400)
    decorate(win)
    pump(app, 800)
    win.fit_page()
    pump(app, 700)
    win._set_tool("highlight")
    win.grab().save(os.path.join(OUT, "main.png"))

    # 多选 + 右键菜单
    win.side.thumbs.clearSelection()
    for i in range(win.side.thumbs.count()):
        win.side.thumbs.item(i).setSelected(True)
    pump(app, 200)
    win.grab().save(os.path.join(OUT, "multi-select.png"))

    menu = win.build_page_menu([0, 1])
    menu.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
    menu.popup(QtCore.QPoint(240, 260))
    pump(app, 400)
    menu.grab().save(os.path.join(OUT, "page-menu.png"))
    menu.close()

    # 水印对话框
    from pdfstudio.ui import dialogs
    dialog = dialogs.WatermarkDialog(win)
    dialog.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
    dialog.show()
    pump(app, 300)
    dialog.grab().save(os.path.join(OUT, "dialog-watermark.png"))
    dialog.close()

    # 目录页签
    win.side.setCurrentIndex(1)
    pump(app, 400)
    win.grab().save(os.path.join(OUT, "outline.png"))

    win.doc.dirty = False
    win.close()
    print("screenshots done")


if __name__ == "__main__":
    main()
