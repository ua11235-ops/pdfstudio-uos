# -*- coding: utf-8 -*-
"""界面主题：浅色、克制、接近 UOS 原生风格的 QSS。"""

import os
import tempfile

from ..qtcompat import QtCore, QtGui, Qt

COLORS = {
    "primary": "#1f6bff",
    "primary_dark": "#1450c8",
    "primary_soft": "#e8f0ff",
    "text": "#1f2329",
    "text_sub": "#6b7280",
    "border": "#e3e6ec",
    "panel": "#ffffff",
    "canvas": "#eceef2",
    "hover": "#f2f4f7",
    "danger": "#e5484d",
}

FONT_STACK = (
    '"Noto Sans CJK SC", "Source Han Sans SC", "Microsoft YaHei UI", '
    '"WenQuanYi Micro Hei", "PingFang SC", sans-serif'
)

QSS_TEMPLATE = """
* { font-family: %(font)s; }

QMainWindow, QDialog { background: %(canvas)s; }
QWidget#CentralHost { background: %(canvas)s; }

QMenuBar {
    background: %(panel)s;
    border-bottom: 1px solid %(border)s;
    padding: 2px 6px;
}
QMenuBar::item { padding: 6px 10px; border-radius: 6px; background: transparent; }
QMenuBar::item:selected { background: %(hover)s; }

QMenu {
    background: %(panel)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    padding: 6px;
}
QMenu::item { padding: 7px 26px 7px 22px; border-radius: 6px; }
QMenu::item:selected { background: %(primary_soft)s; color: %(primary_dark)s; }
QMenu::item:disabled { color: #b6bbc4; }
QMenu::separator { height: 1px; background: %(border)s; margin: 5px 10px; }

QToolBar {
    background: %(panel)s;
    border: none;
    border-bottom: 1px solid %(border)s;
    padding: 5px 8px;
    spacing: 3px;
}
QToolBar::separator { width: 1px; background: %(border)s; margin: 6px 7px; }

QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 5px;
}
QToolButton:hover { background: %(hover)s; }
QToolButton:pressed { background: #e6e9ef; }
QToolButton:checked { background: %(primary_soft)s; border-color: #c3d7ff; }
QToolButton:disabled { opacity: 0.35; }

QStatusBar {
    background: %(panel)s;
    border-top: 1px solid %(border)s;
    color: %(text_sub)s;
}
QStatusBar::item { border: none; }

QDockWidget { color: %(text)s; titlebar-close-icon: none; }
QDockWidget::title {
    background: %(panel)s;
    padding: 7px 10px;
    border-bottom: 1px solid %(border)s;
    text-align: left;
}

QTabWidget::pane { border: none; background: %(panel)s; }
QTabBar::tab {
    background: transparent;
    color: %(text_sub)s;
    padding: 8px 14px;
    border: none;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected { color: %(primary_dark)s; border-bottom: 2px solid %(primary)s; }
QTabBar::tab:hover { color: %(text)s; }

QListWidget, QTreeWidget, QTableWidget {
    background: %(panel)s;
    border: none;
    outline: none;
}
QListWidget::item { padding: 4px; border-radius: 6px; }
QListWidget::item:selected { background: %(primary_soft)s; color: %(text)s; }
QListWidget::item:hover { background: %(hover)s; }

QScrollArea { border: none; background: %(canvas)s; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical {
    background: #c8cdd6; border-radius: 5px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #aab1bd; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: #c8cdd6; border-radius: 5px; min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: #aab1bd; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {
    background: %(panel)s;
    border: 1px solid %(border)s;
    border-radius: 7px;
    padding: 5px 8px;
    selection-background-color: %(primary)s;
    selection-color: #ffffff;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border-color: %(primary)s;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow {
    image: url(%(arrow_down)s);
    width: 10px;
    height: 10px;
    margin-right: 8px;
}

QSpinBox, QDoubleSpinBox { padding-right: 22px; }
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    height: 13px;
    border: none;
    border-left: 1px solid #e3e6ec;
    background: transparent;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    height: 13px;
    border: none;
    border-left: 1px solid #e3e6ec;
    background: transparent;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background: #e9edf3;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url(%(arrow_up)s);
    width: 9px; height: 9px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url(%(arrow_down)s);
    width: 9px; height: 9px;
}

QComboBox QAbstractItemView {
    border: 1px solid %(border)s;
    border-radius: 6px;
    background: %(panel)s;
    selection-background-color: %(primary_soft)s;
    selection-color: %(text)s;
    outline: none;
}

QPushButton {
    background: %(panel)s;
    border: 1px solid %(border)s;
    border-radius: 7px;
    padding: 6px 16px;
    color: %(text)s;
}
QPushButton:hover { background: %(hover)s; }
QPushButton:pressed { background: #e6e9ef; }
QPushButton:default {
    background: %(primary)s;
    border-color: %(primary)s;
    color: #ffffff;
}
QPushButton:default:hover { background: %(primary_dark)s; }
QPushButton:disabled { color: #b6bbc4; background: #f5f6f8; }

QPushButton#PrimaryButton {
    background: %(primary)s;
    color: #ffffff;
    border: none;
    border-radius: 9px;
    padding: 10px 28px;
    font-size: 14px;
    font-weight: 600;
}
QPushButton#PrimaryButton:hover { background: %(primary_dark)s; }
QPushButton#PrimaryButton:pressed { background: #103fa0; }

QCheckBox, QRadioButton { spacing: 7px; color: %(text)s; }
QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; }
QCheckBox::indicator {
    border: 1px solid #c6ccd6; border-radius: 4px; background: %(panel)s;
}
QCheckBox::indicator:checked {
    background: %(primary)s; border-color: %(primary)s;
}

QGroupBox {
    border: 1px solid %(border)s;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 10px;
    background: %(panel)s;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: %(text_sub)s;
}

QSlider::groove:horizontal { height: 4px; background: #dfe3ea; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 14px; height: 14px; margin: -6px 0; border-radius: 7px;
    background: %(primary)s;
}
QSlider::sub-page:horizontal { background: %(primary)s; border-radius: 2px; }

QToolTip {
    background: #2b2f36;
    color: #ffffff;
    border: none;
    padding: 5px 8px;
    border-radius: 6px;
}

QSplitter::handle { background: %(border)s; width: 1px; }
QProgressBar {
    border: none; background: #e9ecf1; border-radius: 4px; height: 8px; text-align: center;
}
QProgressBar::chunk { background: %(primary)s; border-radius: 4px; }
"""


def build_qss(**extra):
    values = dict(COLORS, font=FONT_STACK)
    values.update(extra)
    return QSS_TEMPLATE % values


# 模块级保留一份（未注入图片路径），方便外部引用配色
QSS = build_qss(arrow_up="", arrow_down="")


def _arrow_pixmap(direction, color="#5b6472", size=20):
    """画一个小的 V 形箭头。Qt 的 QSS 不支持 CSS 三角形，只能用图片。"""
    pm = QtGui.QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QtGui.QPainter(pm)
    painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
    pen = QtGui.QPen(QtGui.QColor(color))
    pen.setWidthF(size * 0.16)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    margin = size * 0.28
    if direction == "down":
        painter.drawPolyline([
            QtCore.QPointF(margin, size * 0.38),
            QtCore.QPointF(size / 2.0, size * 0.66),
            QtCore.QPointF(size - margin, size * 0.38),
        ])
    else:
        painter.drawPolyline([
            QtCore.QPointF(margin, size * 0.62),
            QtCore.QPointF(size / 2.0, size * 0.34),
            QtCore.QPointF(size - margin, size * 0.62),
        ])
    painter.end()
    return pm


def _prepare_assets():
    """生成主题用的小图片，返回 QSS 里要用的路径。"""
    folder = os.path.join(tempfile.gettempdir(), "pdfstudio-theme")
    try:
        if not os.path.isdir(folder):
            os.makedirs(folder)
    except OSError:
        folder = os.path.expanduser("~")
    paths = {}
    for direction in ("up", "down"):
        target = os.path.join(folder, "arrow-%s.png" % direction)
        _arrow_pixmap(direction).save(target)
        paths["arrow_" + direction] = target.replace("\\", "/")
    return paths


def apply(app):
    app.setStyle("Fusion")
    app.setStyleSheet(build_qss(**_prepare_assets()))
    palette = app.palette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(COLORS["canvas"]))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(COLORS["text"]))
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(COLORS["panel"]))
    palette.setColor(QtGui.QPalette.Text, QtGui.QColor(COLORS["text"]))
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(COLORS["primary"]))
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#ffffff"))
    app.setPalette(palette)
