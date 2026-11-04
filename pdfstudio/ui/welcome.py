# -*- coding: utf-8 -*-
"""欢迎页：没有打开文档时显示。"""

from ..qtcompat import QtCore, QtGui, QtWidgets, Qt, Signal

from . import icons
from .theme import COLORS


class WelcomeWidget(QtWidgets.QWidget):
    openRequested = Signal()

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.setObjectName("CentralHost")

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.addStretch(1)

        card = QtWidgets.QWidget()
        card.setMaximumWidth(460)
        box = QtWidgets.QVBoxLayout(card)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        box.setAlignment(Qt.AlignHCenter)

        logo = QtWidgets.QLabel()
        logo.setPixmap(icons.app_icon(88))
        logo.setAlignment(Qt.AlignCenter)
        box.addWidget(logo)
        box.addSpacing(22)

        title = QtWidgets.QLabel("PDF 工作台")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 24px; font-weight: 600; color: %s; letter-spacing: 1px;"
            % COLORS["text"]
        )
        box.addWidget(title)
        box.addSpacing(10)

        subtitle = QtWidgets.QLabel("阅读 · 批注 · 改字 · 水印 · 加密 · 脱敏")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            "font-size: 13px; color: %s; line-height: 20px;" % COLORS["text_sub"]
        )
        box.addWidget(subtitle)
        box.addSpacing(28)

        self.open_button = QtWidgets.QPushButton("打开 PDF 文件")
        self.open_button.setObjectName("PrimaryButton")
        self.open_button.setCursor(Qt.PointingHandCursor)
        self.open_button.setFixedHeight(42)
        self.open_button.setMinimumWidth(200)
        self.open_button.clicked.connect(self.openRequested)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.open_button)
        row.addStretch(1)
        box.addLayout(row)

        box.addSpacing(18)

        hint = QtWidgets.QLabel("也可以把 PDF 直接拖进窗口，或按 Ctrl+O")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size: 12px; color: #9aa1ad;")
        box.addWidget(hint)

        outer.addWidget(card, 0, Qt.AlignHCenter)
        outer.addStretch(2)

        footer = QtWidgets.QLabel("支持统信 UOS / 深度 Deepin / 麒麟 等国产操作系统")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("font-size: 11px; color: #a8aeb8;")
        outer.addWidget(footer)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(COLORS["canvas"]))
        painter.end()
