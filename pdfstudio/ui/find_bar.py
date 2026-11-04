# -*- coding: utf-8 -*-
"""顶部查找栏。"""

from ..qtcompat import QtCore, QtWidgets, Qt, Signal

from . import icons
from .theme import COLORS


class FindBar(QtWidgets.QWidget):
    searchRequested = Signal(str)
    nextRequested = Signal()
    prevRequested = Signal()
    closed = Signal()

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.setObjectName("FindBar")
        self.setStyleSheet(
            "#FindBar { background: %s; border-bottom: 1px solid %s; }"
            % (COLORS["panel"], COLORS["border"])
        )
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(8)

        self.edit = QtWidgets.QLineEdit()
        self.edit.setPlaceholderText("在文档中查找…")
        self.edit.setClearButtonEnabled(True)
        self.edit.setMinimumWidth(220)
        self.edit.setMaximumWidth(320)
        layout.addWidget(self.edit)

        self.count = QtWidgets.QLabel("")
        self.count.setStyleSheet("color: %s; font-size: 12px;" % COLORS["text_sub"])
        self.count.setMinimumWidth(90)
        layout.addWidget(self.count)

        self.prev_btn = QtWidgets.QToolButton()
        self.prev_btn.setIcon(icons.icon("prev", 16))
        self.prev_btn.setToolTip("上一个（Shift+Enter）")
        layout.addWidget(self.prev_btn)

        self.next_btn = QtWidgets.QToolButton()
        self.next_btn.setIcon(icons.icon("next", 16))
        self.next_btn.setToolTip("下一个（Enter）")
        layout.addWidget(self.next_btn)

        layout.addStretch(1)

        close_btn = QtWidgets.QToolButton()
        close_btn.setText("✕")
        close_btn.setToolTip("关闭（Esc）")
        close_btn.clicked.connect(self.hide_bar)
        layout.addWidget(close_btn)

        self.edit.returnPressed.connect(self._on_return)
        self.edit.textChanged.connect(self._on_text_changed)
        self.prev_btn.clicked.connect(self.prevRequested)
        self.next_btn.clicked.connect(self.nextRequested)

    def _on_return(self):
        if QtWidgets.QApplication.keyboardModifiers() & Qt.ShiftModifier:
            self.prevRequested.emit()
        else:
            self.nextRequested.emit()

    def _on_text_changed(self, text):
        if not text:
            self.count.setText("")
        else:
            self.searchRequested.emit(text)

    def set_count(self, current, total):
        if total <= 0:
            self.count.setText("无结果")
            self.count.setStyleSheet("color: %s; font-size: 12px;" % COLORS["danger"])
        else:
            self.count.setText("%d / %d" % (current, total))
            self.count.setStyleSheet("color: %s; font-size: 12px;" % COLORS["text_sub"])

    def focus_edit(self, preset=""):
        self.show()
        if preset:
            self.edit.setText(preset)
        self.edit.setFocus()
        self.edit.selectAll()

    def hide_bar(self):
        self.hide()
        self.closed.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide_bar()
            return
        QtWidgets.QWidget.keyPressEvent(self, event)
