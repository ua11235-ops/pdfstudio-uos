# -*- coding: utf-8 -*-
"""主窗口：菜单、工具栏、侧栏、状态栏以及所有业务动作的编排。"""

import os

from ..qtcompat import (
    QtCore, QtGui, QtWidgets, Qt, QAction, QActionGroup, QShortcut, Signal, qexec, RGB888,
    QPrinter, QPrintDialog,
)

from .. import APP_NAME, APP_NAME_CN, __version__
from ..core import annotate as annot_mod
from ..core import decorate, export as export_mod, pageops, security, textops
from ..core.document import PdfDocument, PdfError

from . import dialogs, icons
from .find_bar import FindBar
from .merge_dialog import MergeDialog
from .page_view import PageView, TOOLS, TOOL_NAMES
from .side_panel import SidePanel
from .welcome import WelcomeWidget
from .theme import COLORS

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz


ZOOM_PRESETS = [("50%", 0.5), ("75%", 0.75), ("100%", 1.0), ("125%", 1.25),
                ("150%", 1.5), ("200%", 2.0), ("300%", 3.0), ("400%", 4.0)]


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, path=None):
        QtWidgets.QMainWindow.__init__(self)
        self.doc = PdfDocument()
        self.doc.add_listener(self._on_doc_event)

        self._find_hits = []
        self._find_index = -1
        self._syncing = False
        self._fit_mode = None  # None / "width" / "page"
        self.actions = {}

        self.setWindowTitle("%s · %s" % (APP_NAME_CN, APP_NAME))
        self.setWindowIcon(QtGui.QIcon(icons.app_icon(128)))
        self.resize(1280, 860)
        self.setAcceptDrops(True)
        self.setMinimumSize(940, 620)

        self._build_center()
        self._build_statusbar()
        self._build_actions()
        self._build_menus()
        self._build_toolbars()
        self._build_dock()
        self._wire()

        self._panel_timer = QtCore.QTimer(self)
        self._panel_timer.setSingleShot(True)
        self._panel_timer.setInterval(350)
        self._panel_timer.timeout.connect(self._refresh_panels)

        self._sync_ui()
        if path:
            QtCore.QTimer.singleShot(60, lambda: self.open_path(path))

    # ------------------------------------------------------------------
    # 界面搭建
    # ------------------------------------------------------------------
    def _build_center(self):
        self.page_view = PageView()
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidget(self.page_view)
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.page_view.attach_scroll_area(self.scroll)
        self.scroll.viewport().installEventFilter(self)

        self.find_bar = FindBar()
        self.find_bar.hide()

        self.welcome = WelcomeWidget()
        self.welcome.openRequested.connect(self.open_dialog)

        self.stack = QtWidgets.QStackedWidget()
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.scroll)

        host = QtWidgets.QWidget()
        host.setObjectName("CentralHost")
        layout = QtWidgets.QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.find_bar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(host)

    def _act(self, key, text, icon_name=None, shortcut=None, tip=None,
             checkable=False, slot=None, data=None):
        action = QAction(text, self)
        if icon_name:
            action.setIcon(icons.icon(icon_name, 20))
        if shortcut:
            action.setShortcut(QtGui.QKeySequence(shortcut))
        action.setToolTip(tip or text)
        action.setStatusTip(tip or text)
        action.setCheckable(checkable)
        if data is not None:
            action.setData(data)
        if slot is not None:
            if checkable:
                action.toggled.connect(slot)
            else:
                action.triggered.connect(slot)
        self.actions[key] = action
        self.addAction(action)
        return action

    def _build_actions(self):
        a = self._act
        a("open", "打开…", "open", "Ctrl+O", "打开 PDF 文件", slot=self.open_dialog)
        a("merge_files", "合并 PDF 文件…", "merge", "Ctrl+M",
          "把多个 PDF 合成一个文件，可拖拽调整页序", slot=self.merge_files)
        a("save", "保存", "save", "Ctrl+S", "保存到当前文件", slot=self.save_file)
        a("saveas", "另存为…", "saveas", "Ctrl+Shift+S", "另存为新文件", slot=self.save_file_as)
        a("print", "打印…", "print", "Ctrl+P", "打印当前文档", slot=self.print_document)
        a("export_img", "导出为图片…", "export", None, "把页面导出成 PNG / JPEG", slot=self.export_images)
        a("export_txt", "导出文本…", "export", None, "把文字内容导出为 txt", slot=self.export_text)
        a("export_long", "导出长图…", "export", None, "多页拼成一张长图", slot=self.export_long_image)
        a("compress", "压缩文档…", "grid", None, "减小文件体积", slot=self.compress_document)
        a("props", "文档属性…", "info", None, "查看和修改标题、作者等信息", slot=self.edit_metadata)
        a("quit", "退出", None, "Ctrl+Q", "退出程序", slot=self.close)

        a("undo", "撤销", "undo", "Ctrl+Z", "撤销上一步操作", slot=self.undo)
        a("redo", "重做", "redo", "Ctrl+Shift+Z", "重做", slot=self.redo)
        a("copy", "复制选中文字", "text_select", "Ctrl+C", "复制框选的文字", slot=self.copy_selection)
        a("delete_annot", "删除选中注释", "trash", "Delete", "删除当前选中的注释", slot=self.delete_selected_annot)
        a("find", "查找…", "search", "Ctrl+F", "在文档中查找文字", slot=self.show_find)

        a("page_insert", "插入空白页", "plus", None, "在当前页之后插入空白页", slot=self.insert_blank_page)
        a("page_insert_file", "插入其他文件…", "merge", None, "把另一个 PDF 的页面插入进来", slot=self.insert_from_file)
        a("page_delete", "删除当前页", "trash", "Ctrl+Shift+Delete", "删除当前页面", slot=self.delete_page)
        a("rotate_l", "向左旋转", "rotate_l", "Ctrl+Shift+L", "当前页逆时针旋转 90°", slot=lambda: self.rotate(-90))
        a("rotate_r", "向右旋转", "rotate_r", "Ctrl+Shift+R", "当前页顺时针旋转 90°", slot=lambda: self.rotate(90))
        a("rotate_180", "旋转 180°", "rotate_r", None, "当前页倒转 180°", slot=lambda: self.rotate(180))
        a("page_extract", "提取页面…", "split", None, "把选中的页面另存为文件", slot=self.extract_pages)
        a("page_split", "拆分文档…", "split", None, "按页或按范围拆成多个文件", slot=self.split_document)
        a("page_merge", "合并到当前文档…", "merge", None, "追加其他 PDF 的所有页面", slot=self.merge_into)

        a("watermark", "添加水印…", "watermark", None, "在页面上叠加水印文字", slot=self.add_watermark)
        a("page_numbers", "添加页码…", "pages", None, "给页面添加页码", slot=self.add_page_numbers)
        a("encrypt", "加密文档…", "lock", None, "为文档设置打开密码", slot=self.encrypt_document)
        a("decrypt", "移除密码…", "unlock", None, "另存为无密码副本", slot=self.decrypt_document)
        a("redact", "按内容涂黑…", "redact", None, "永久删除指定文字（脱敏）", slot=self.redact_text)
        a("form", "填写表单…", "form", None, "填写 PDF 中的表单字段", slot=self.fill_form)
        a("ocr", "OCR 识别当前页", "search", None, "识别扫描件上的文字", slot=self.ocr_page)

        a("zoom_in", "放大", "zoom_in", "Ctrl+=", "放大页面", slot=lambda: self.zoom_by(1.2))
        a("zoom_out", "缩小", "zoom_out", "Ctrl+-", "缩小页面", slot=lambda: self.zoom_by(1 / 1.2))
        a("fit_width", "适应宽度", "fit_width", "Ctrl+1", "页面宽度铺满窗口", slot=self.fit_width)
        a("fit_page", "整页显示", "fit_page", "Ctrl+2", "完整显示一整页", slot=self.fit_page)
        a("actual", "实际大小", None, "Ctrl+0", "100% 显示", slot=lambda: self._manual_zoom(value=1.0))

        a("toggle_sidebar", "显示侧栏", "thumbnails", "F9", "显示 / 隐藏左侧面板",
          checkable=True, slot=self._toggle_sidebar)
        a("about", "关于 %s" % APP_NAME, "info", None, "版本信息", slot=self.show_about)

        # 工具切换（互斥）
        tool_group = QActionGroup(self)
        tool_group.setExclusive(True)
        shortcuts = {"select": "V", "hand": "H", "text_select": "T", "edit_text": "E",
                     "highlight": "G", "underline": "U", "strikeout": "D", "ink": "P",
                     "rect": "R", "ellipse": "O", "arrow": "A", "freetext": "F",
                     "note": "N", "redact": "B", "eraser": "X"}
        for key, label, icon_name, _hint in TOOLS:
            action = self._act("tool_" + key, label, icon_name,
                               shortcuts.get(key), _hint, checkable=True,
                               slot=(lambda checked, k=key: checked and self._set_tool(k)))
            tool_group.addAction(action)
        self.actions["tool_select"].setChecked(True)

    def _build_menus(self):
        bar = self.menuBar()
        a = self.actions

        m_file = bar.addMenu("文件(&F)")
        m_file.addAction(a["open"])
        m_file.addAction(a["merge_files"])
        m_file.addSeparator()
        m_file.addAction(a["save"])
        m_file.addAction(a["saveas"])
        m_file.addSeparator()
        m_export = m_file.addMenu("导出")
        m_export.addAction(a["export_img"])
        m_export.addAction(a["export_txt"])
        m_export.addAction(a["export_long"])
        m_file.addAction(a["compress"])
        m_file.addSeparator()
        m_file.addAction(a["print"])
        m_file.addAction(a["props"])
        m_file.addSeparator()
        m_file.addAction(a["quit"])

        m_edit = bar.addMenu("编辑(&E)")
        m_edit.addAction(a["undo"])
        m_edit.addAction(a["redo"])
        m_edit.addSeparator()
        m_edit.addAction(a["copy"])
        m_edit.addAction(a["delete_annot"])
        m_edit.addSeparator()
        m_edit.addAction(a["find"])

        m_page = bar.addMenu("页面(&P)")
        m_page.addAction(a["page_insert"])
        m_page.addAction(a["page_insert_file"])
        m_page.addAction(a["page_delete"])
        m_page.addSeparator()
        m_page.addAction(a["rotate_l"])
        m_page.addAction(a["rotate_r"])
        m_page.addAction(a["rotate_180"])
        m_page.addSeparator()
        m_page.addAction(a["page_extract"])
        m_page.addAction(a["page_split"])
        m_page.addAction(a["page_merge"])
        m_page.addAction(a["merge_files"])

        m_tools = bar.addMenu("工具(&T)")
        m_tools.addAction(a["watermark"])
        m_tools.addAction(a["page_numbers"])
        m_tools.addSeparator()
        m_tools.addAction(a["redact"])
        m_tools.addAction(a["form"])
        m_tools.addAction(a["ocr"])
        m_tools.addSeparator()
        m_tools.addAction(a["encrypt"])
        m_tools.addAction(a["decrypt"])

        m_view = bar.addMenu("视图(&V)")
        m_view.addAction(a["zoom_in"])
        m_view.addAction(a["zoom_out"])
        m_view.addAction(a["fit_width"])
        m_view.addAction(a["fit_page"])
        m_view.addAction(a["actual"])
        m_view.addSeparator()
        m_view.addAction(a["toggle_sidebar"])

        m_help = bar.addMenu("帮助(&H)")
        m_help.addAction(a["about"])

    def _build_toolbars(self):
        bar = QtWidgets.QToolBar("主工具栏")
        bar.setObjectName("MainToolBar")
        bar.setMovable(False)
        bar.setIconSize(QtCore.QSize(20, 20))
        bar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        a = self.actions

        bar.addAction(a["open"])
        bar.addAction(a["save"])
        bar.addSeparator()
        bar.addAction(a["undo"])
        bar.addAction(a["redo"])
        bar.addSeparator()
        bar.addAction(QtGui.QIcon(icons.pixmap("first", 16)), "首页", self.first_page)
        bar.addAction(QtGui.QIcon(icons.pixmap("prev", 16)), "上一页", lambda: self.goto_page(self.page_view.page_index - 1))

        self.page_spin = QtWidgets.QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.setFixedWidth(64)
        self.page_spin.setFixedHeight(26)
        self.page_spin.setAlignment(Qt.AlignCenter)
        self.page_spin.setToolTip("跳转到指定页")
        self.page_spin.valueChanged.connect(self._on_page_spin)
        bar.addWidget(self.page_spin)
        self.page_total = QtWidgets.QLabel(" / 0 ")
        self.page_total.setStyleSheet("color: %s; padding-right: 4px;" % COLORS["text_sub"])
        bar.addWidget(self.page_total)

        bar.addAction(QtGui.QIcon(icons.pixmap("next", 16)), "下一页", lambda: self.goto_page(self.page_view.page_index + 1))
        bar.addAction(QtGui.QIcon(icons.pixmap("last", 16)), "末页", self.last_page)
        bar.addSeparator()
        bar.addAction(a["zoom_out"])

        self.zoom_button = QtWidgets.QToolButton()
        self.zoom_button.setText("100%")
        self.zoom_button.setToolTip("缩放比例")
        self.zoom_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.zoom_button.setFixedWidth(70)
        self.zoom_button.setStyleSheet("QToolButton { padding: 4px 6px; }")
        zoom_menu = QtWidgets.QMenu(self.zoom_button)
        for label, value in ZOOM_PRESETS:
            act = zoom_menu.addAction(label)
            act.triggered.connect(lambda _checked=False, v=value: self._manual_zoom(value=v))
        zoom_menu.addSeparator()
        zoom_menu.addAction(a["fit_width"])
        zoom_menu.addAction(a["fit_page"])
        self.zoom_button.setMenu(zoom_menu)
        bar.addWidget(self.zoom_button)

        bar.addAction(a["zoom_in"])
        bar.addAction(a["fit_width"])
        bar.addSeparator()
        bar.addAction(a["find"])
        self.addToolBar(Qt.TopToolBarArea, bar)
        self.main_toolbar = bar

        self.addToolBarBreak(Qt.TopToolBarArea)
        tools = QtWidgets.QToolBar("标注工具")
        tools.setObjectName("ToolsToolBar")
        tools.setMovable(False)
        tools.setIconSize(QtCore.QSize(20, 20))
        for key, label, _icon, _hint in TOOLS:
            tools.addAction(self.actions["tool_" + key])
        tools.addSeparator()

        self.color_button = QtWidgets.QToolButton()
        self.color_button.setToolTip("标注颜色")
        self.color_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.color_button.setIconSize(QtCore.QSize(18, 18))
        color_menu = QtWidgets.QMenu(self.color_button)
        for label, rgb in annot_mod.COLOR_PRESETS:
            pix = QtGui.QPixmap(18, 18)
            pix.fill(QtGui.QColor(int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)))
            act = color_menu.addAction(QtGui.QIcon(pix), label)
            act.triggered.connect(lambda _checked=False, c=rgb: self._set_color(c))
        self.color_button.setMenu(color_menu)
        tools.addWidget(self.color_button)
        self._set_color(annot_mod.COLOR_PRESETS[0][1])

        self.width_spin = QtWidgets.QSpinBox()
        self.width_spin.setRange(1, 20)
        self.width_spin.setValue(2)
        self.width_spin.setFixedWidth(58)
        self.width_spin.setFixedHeight(26)
        self.width_spin.setSuffix(" px")
        self.width_spin.setToolTip("线条粗细")
        self.width_spin.valueChanged.connect(lambda v: self.page_view.set_style(line_width=float(v)))
        tools.addWidget(self.width_spin)

        tools.addSeparator()
        tools.addAction(self.actions["redact"])
        tools.addAction(self.actions["delete_annot"])
        self.addToolBar(Qt.TopToolBarArea, tools)
        self.tool_toolbar = tools

    def _build_dock(self):
        self.side = SidePanel()
        self.dock = QtWidgets.QDockWidget("导航", self)
        self.dock.setObjectName("SideDock")
        self.dock.setWidget(self.side)
        self.dock.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable |
                              QtWidgets.QDockWidget.DockWidgetClosable)
        self.dock.setMinimumWidth(180)
        self.dock.setMaximumWidth(260)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock)
        self.actions["toggle_sidebar"].setChecked(True)

    def _build_statusbar(self):
        bar = self.statusBar()
        self.status_label = QtWidgets.QLabel("就绪")
        self.status_label.setStyleSheet("color: %s;" % COLORS["text_sub"])
        bar.addWidget(self.status_label, 1)

        self.tool_label = QtWidgets.QLabel("")
        self.tool_label.setStyleSheet("color: %s;" % COLORS["text_sub"])
        bar.addPermanentWidget(self.tool_label)

        self.size_label = QtWidgets.QLabel("")
        self.size_label.setStyleSheet("color: %s;" % COLORS["text_sub"])
        bar.addPermanentWidget(self.size_label)

        self.zoom_label = QtWidgets.QLabel("100%")
        self.zoom_label.setMinimumWidth(52)
        self.zoom_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bar.addPermanentWidget(self.zoom_label)

    def _wire(self):
        self.page_view.pageChanged.connect(self._on_page_changed)
        self.page_view.zoomChanged.connect(self._on_zoom_changed)
        self.page_view.modified.connect(self._on_modified)
        self.page_view.hintChanged.connect(self.status_label.setText)
        self.page_view.selectionChanged.connect(self._on_selection_changed)

        self.side.pageActivated.connect(self.goto_page)
        self.side.contextRequested.connect(self._page_menu)
        self.side.annotationActivated.connect(self._goto_annotation)
        self.side.pagesReordered.connect(self.reorder_pages)

        self.find_bar.searchRequested.connect(self.run_search)
        self.find_bar.nextRequested.connect(lambda: self.step_search(1))
        self.find_bar.prevRequested.connect(lambda: self.step_search(-1))

        shortcut_close = QShortcut(QtGui.QKeySequence("Ctrl+W"), self)
        shortcut_close.activated.connect(self.close)
        shortcut_esc = QShortcut(QtGui.QKeySequence("Esc"), self)
        shortcut_esc.activated.connect(self._on_escape)

    # ------------------------------------------------------------------
    # 状态同步
    # ------------------------------------------------------------------
    def _sync_ui(self):
        opened = self.doc.is_open
        for key in ("save", "saveas", "print", "export_img", "export_txt", "export_long",
                    "compress", "props", "find", "page_insert", "page_insert_file",
                    "page_delete", "rotate_l", "rotate_r", "rotate_180", "page_extract", "page_split",
                    "page_merge", "watermark", "page_numbers", "encrypt", "decrypt",
                    "redact", "form", "ocr", "copy", "delete_annot",
                    "zoom_in", "zoom_out", "fit_width", "fit_page", "actual"):
            if key in self.actions:
                self.actions[key].setEnabled(opened)
        self.actions["undo"].setEnabled(opened and self.doc.can_undo())
        self.actions["redo"].setEnabled(opened and self.doc.can_redo())
        for key, _label, _icon, _hint in TOOLS:
            self.actions["tool_" + key].setEnabled(opened)
        self.width_spin.setEnabled(opened)
        self.color_button.setEnabled(opened)
        self.page_spin.setEnabled(opened)

        self.stack.setCurrentIndex(1 if opened else 0)
        # 没有文档时收起侧栏，让欢迎页保持干净
        self.dock.setVisible(bool(opened) and self.actions["toggle_sidebar"].isChecked())
        if opened:
            self._syncing = True
            self.page_spin.setRange(1, self.doc.page_count)
            self.page_spin.setValue(self.page_view.page_index + 1)
            self.page_total.setText(" / %d " % self.doc.page_count)
            self._syncing = False
            name = self.doc.display_name
            mark = " *" if self.doc.dirty else ""
            self.setWindowTitle("%s%s — %s" % (name, mark, APP_NAME_CN))
            width, height = self.doc.page_size(self.page_view.page_index)
            size = export_mod.file_size(self.doc.path) if self.doc.path else 0
            self.size_label.setText("%.0f × %.0f pt · %s" % (
                width, height, export_mod.human_size(size)))
        else:
            self.setWindowTitle("%s · %s" % (APP_NAME_CN, APP_NAME))
            self.page_total.setText(" / 0 ")
            self.size_label.setText("")
        self._update_undo_text()

    def _update_undo_text(self):
        undo = self.actions["undo"]
        redo = self.actions["redo"]
        undo.setText("撤销" + ("：" + self.doc.undo_label() if self.doc.can_undo() else ""))
        redo.setText("重做" + ("：" + self.doc.redo_label() if self.doc.can_redo() else ""))

    def _on_doc_event(self, what):
        if what in ("open", "close", "saved"):
            self.page_view.set_document(self.doc if self.doc.is_open else None)
            self.side.set_document(self.doc if self.doc.is_open else None)
        else:
            self.page_view.reload()
            self._panel_timer.start()
        self._sync_ui()

    def _refresh_panels(self):
        if self.doc.is_open:
            self.side.refresh()
            self.side.annots.set_annotations(annot_mod.list_annotations(self.doc))
            self.side.thumbs.set_current_page(self.page_view.page_index)

    def _on_page_changed(self, index):
        if self._syncing:
            return
        self._syncing = True
        self.page_spin.setValue(index + 1)
        self._syncing = False
        self.side.thumbs.set_current_page(index)
        self.actions["delete_annot"].setEnabled(False)
        self._sync_ui()
        if self.doc.is_open:
            width, height = self.doc.page_size(index)
            self.size_label.setText("%.0f × %.0f pt" % (width, height))

    def _on_zoom_changed(self, zoom):
        text = "%d%%" % int(round(zoom * 100))
        self.zoom_label.setText(text)
        self.zoom_button.setText(text)

    def _on_modified(self, label):
        self.status_label.setText("%s 已完成" % label)
        self._panel_timer.start()
        self._sync_ui()

    def _on_selection_changed(self, item):
        self.actions["delete_annot"].setEnabled(item is not None)
        if item is None:
            return
        self.status_label.setText("已选中%s%s" % (
            item["type_cn"], ("：" + item["content"][:40]) if item["content"] else ""))

    # ------------------------------------------------------------------
    # 文件
    # ------------------------------------------------------------------
    def open_dialog(self):
        if not self._maybe_save():
            return
        path, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self, "打开 PDF", "", "PDF 文件 (*.pdf);;所有文件 (*)")
        if path:
            self.open_path(path)

    def merge_files(self):
        """合并多个 PDF 成一个新文件。

        不依赖当前文档：没打开任何文件时也能用，所以这个动作不进 _sync_ui
        的"需要有文档才启用"列表。
        """
        if not self._maybe_save():
            return
        default_dir = os.path.dirname(self.doc.path) if self.doc.path else None
        dialog = MergeDialog(self, default_dir=default_dir)
        if not dialog.exec_dialog():
            return
        path = dialog.result_path()
        if not path:
            return
        self.status_label.setText("已合并到 %s" % path)
        answer = QtWidgets.QMessageBox.question(
            self, "合并完成",
            "已生成：\n%s\n\n现在打开它吗？" % path,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes)
        if answer == QtWidgets.QMessageBox.Yes:
            self.open_path(path)

    def open_path(self, path):
        if not self._maybe_save():
            return
        try:
            self.doc.open(path)
        except PdfError as exc:
            if exc.code == "password":
                password, ok = QtWidgets.QInputDialog.getText(
                    self, "需要密码", "该文档已加密，请输入打开密码：",
                    QtWidgets.QLineEdit.Password)
                if not ok or not password:
                    return
                try:
                    self.doc.open(path, password)
                except PdfError as exc2:
                    QtWidgets.QMessageBox.warning(self, "无法打开", str(exc2))
                    return
            else:
                QtWidgets.QMessageBox.warning(self, "无法打开", str(exc))
                return
        QtCore.QTimer.singleShot(0, self._after_open)

    def _after_open(self):
        self.page_view.set_document(self.doc)
        self.stack.setCurrentIndex(1)
        self.side.set_document(self.doc)
        self.page_view.set_tool(self.page_view.tool)
        self._fit_mode = "width"
        QtCore.QTimer.singleShot(60, self.page_view.fit_width)
        self.status_label.setText("已打开 %s，共 %d 页" % (self.doc.display_name, self.doc.page_count))
        self._refresh_panels()

    def save_file(self):
        if not self.doc.is_open:
            return False
        if not self.doc.path:
            return self.save_file_as()
        try:
            self.doc.save()
        except PdfError as exc:
            QtWidgets.QMessageBox.warning(self, "保存失败", str(exc))
            return False
        self.status_label.setText("已保存到 %s" % self.doc.path)
        return True

    def save_file_as(self):
        if not self.doc.is_open:
            return False
        default = self.doc.path or os.path.join(os.path.expanduser("~"), "未命名.pdf")
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "另存为", default, "PDF 文件 (*.pdf)")
        if not path:
            return False
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            self.doc.save(path)
        except PdfError as exc:
            QtWidgets.QMessageBox.warning(self, "保存失败", str(exc))
            return False
        self.status_label.setText("已另存为 %s" % path)
        return True

    def _maybe_save(self):
        if not self.doc.is_open or not self.doc.dirty:
            return True
        answer = QtWidgets.QMessageBox.question(
            self, "尚未保存",
            "《%s》有未保存的修改，要先保存吗？" % self.doc.display_name,
            QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard |
            QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Save,
        )
        if answer == QtWidgets.QMessageBox.Cancel:
            return False
        if answer == QtWidgets.QMessageBox.Save:
            return self.save_file()
        return True

    def closeEvent(self, event):
        if self._maybe_save():
            self.doc.close()
            event.accept()
        else:
            event.ignore()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self.open_path(path)
                return

    # ------------------------------------------------------------------
    # 视图
    # ------------------------------------------------------------------
    def goto_page(self, index):
        if not self.doc.is_open:
            return
        index = max(0, min(index, self.doc.page_count - 1))
        self.page_view.set_page(index)

    def first_page(self):
        self.goto_page(0)

    def last_page(self):
        self.goto_page(self.doc.page_count - 1)

    def _on_page_spin(self, value):
        if self._syncing:
            return
        self.goto_page(value - 1)

    def zoom_by(self, factor):
        if self.doc.is_open:
            self._manual_zoom(factor=factor)

    def fit_width(self):
        if not self.doc.is_open:
            return
        self._fit_mode = "width"
        self.page_view.fit_width()

    def fit_page(self):
        if not self.doc.is_open:
            return
        self._fit_mode = "page"
        self.page_view.fit_page()

    def _apply_fit(self):
        if not self.doc.is_open or not self._fit_mode:
            return
        if self._fit_mode == "width":
            self.page_view.fit_width()
        else:
            self.page_view.fit_page()

    def _manual_zoom(self, value=None, factor=None):
        """手动缩放时退出"自动适应"状态。"""
        self._fit_mode = None
        if factor is not None:
            self.page_view.set_zoom(self.page_view.zoom * factor)
        elif value is not None:
            self.page_view.set_zoom(value)

    def eventFilter(self, obj, event):
        if obj is self.scroll.viewport() and event.type() == QtCore.QEvent.Resize:
            if self._fit_mode and self.doc.is_open:
                QtCore.QTimer.singleShot(0, self._apply_fit)
        return QtWidgets.QMainWindow.eventFilter(self, obj, event)

    def _toggle_sidebar(self, checked):
        self.dock.setVisible(bool(checked) and self.doc.is_open)

    def _set_tool(self, key):
        self.page_view.set_tool(key)
        self.tool_label.setText(TOOL_NAMES.get(key, ""))

    def _set_color(self, rgb):
        self.page_view.set_style(color=rgb)
        pix = QtGui.QPixmap(18, 18)
        pix.fill(QtGui.QColor(int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)))
        painter = QtGui.QPainter(pix)
        painter.setPen(QtGui.QPen(QtGui.QColor("#c9ced8"), 1))
        painter.drawRect(0, 0, 17, 17)
        painter.end()
        self.color_button.setIcon(QtGui.QIcon(pix))

    def _on_escape(self):
        if self.find_bar.isVisible():
            self.find_bar.hide_bar()
            return
        self.page_view.clear_text_selection()

    # ------------------------------------------------------------------
    # 编辑
    # ------------------------------------------------------------------
    def undo(self):
        if self.doc.is_open and self.doc.undo():
            self.status_label.setText("已撤销")
            self._sync_ui()

    def redo(self):
        if self.doc.is_open and self.doc.redo():
            self.status_label.setText("已重做")
            self._sync_ui()

    def copy_selection(self):
        text = self.page_view.selection_text()
        if not text:
            text = self.page_view.selected_annotation_content()
        if text:
            QtWidgets.QApplication.clipboard().setText(text)
            self.status_label.setText("已复制 %d 个字符" % len(text))
        else:
            self.status_label.setText("没有可复制的文字，先用「选择文字」工具框选")

    def delete_selected_annot(self):
        xref = self.page_view.selected_xref()
        if xref is None:
            self.status_label.setText("请先选中一个注释")
            return
        self.page_view._delete_annotation(xref)

    # ------------------------------------------------------------------
    # 查找
    # ------------------------------------------------------------------
    def show_find(self):
        if not self.doc.is_open:
            return
        preset = self.page_view.selection_text()
        self.find_bar.focus_edit(preset[:60] if preset else "")

    def run_search(self, text):
        if not self.doc.is_open:
            return
        self._find_hits = self.doc.search(text, start_page=self.page_view.page_index)
        self._find_index = -1
        if not self._find_hits:
            self.find_bar.set_count(0, 0)
            self.page_view.set_search_hits([])
            return
        self.step_search(1)

    def step_search(self, step):
        if not self._find_hits:
            return
        self._find_index = (self._find_index + step) % len(self._find_hits)
        page_index, rect = self._find_hits[self._find_index]
        hits_on_page = [r for p, r in self._find_hits if p == page_index]
        self.page_view.goto_hit(page_index, rect)
        self.page_view.set_search_hits(hits_on_page)
        self.find_bar.set_count(self._find_index + 1, len(self._find_hits))

    # ------------------------------------------------------------------
    # 页面操作
    # ------------------------------------------------------------------
    def insert_blank_page(self):
        try:
            self.page_view.insert_blank()
        except PdfError as exc:
            QtWidgets.QMessageBox.warning(self, "插入失败", str(exc))

    def delete_page(self):
        self.delete_pages([self.page_view.page_index])

    # ---------------- 批量页面操作（缩略图右键菜单 / 页面菜单共用） ----------------
    def _page_menu(self, pages, global_pos):
        menu = self.build_page_menu(pages)
        if menu is None:
            return
        trigger = getattr(menu, "exec", None) or getattr(menu, "exec_")
        trigger(global_pos)

    def build_page_menu(self, pages):
        """构造缩略图右键菜单（拆出来便于测试与复用）。"""
        if not self.doc.is_open:
            return None
        pages = list(pages) or [self.page_view.page_index]
        count = len(pages)
        menu = QtWidgets.QMenu(self)

        menu.addAction("在此页之后插入空白页", lambda: self.insert_blank_after(pages[-1]))
        menu.addAction("从文件插入页面…", self.insert_from_file)
        menu.addSeparator()
        label = ("删除所选 %d 页" % count) if count > 1 else "删除此页"
        menu.addAction(label, lambda: self.delete_pages(pages))
        menu.addSeparator()
        menu.addAction("顺时针旋转 90°", lambda: self.rotate_pages(pages, 90))
        menu.addAction("逆时针旋转 90°", lambda: self.rotate_pages(pages, -90))
        menu.addAction("旋转 180°", lambda: self.rotate_pages(pages, 180))
        menu.addSeparator()
        if count == 1:
            menu.addAction("上移一页", lambda: self.move_page_by(pages[0], -1))
            menu.addAction("下移一页", lambda: self.move_page_by(pages[0], 1))
            menu.addAction("移到文档开头", lambda: self.move_page_to(pages[0], 0))
            menu.addAction("移到文档末尾", lambda: self.move_page_to(pages[0], self.doc.page_count - 1))
            menu.addSeparator()
        menu.addAction("提取所选页面…", lambda: self.extract_selected(pages))
        menu.addAction("导出所选为图片…", lambda: self.export_selected_images(pages))
        return menu

    def insert_blank_after(self, index):
        self.doc.begin_change("插入空白页")
        try:
            pageops.insert_blank_page(self.doc, index + 1)
        except PdfError as exc:
            self.doc.undo()
            QtWidgets.QMessageBox.warning(self, "插入失败", str(exc))
            return
        self.doc.end_change()
        self.page_view.set_page(index + 1)
        self.status_label.setText("已插入 1 页空白页")

    def delete_pages(self, pages):
        pages = sorted(set(pages))
        if not pages:
            return
        if len(pages) >= self.doc.page_count:
            QtWidgets.QMessageBox.warning(self, "无法删除", "不能删除全部页面，至少要保留一页。")
            return
        self.doc.begin_change("删除页面")
        try:
            pageops.delete_pages(self.doc, pages)
        except PdfError as exc:
            self.doc.undo()
            QtWidgets.QMessageBox.warning(self, "无法删除", str(exc))
            return
        self.doc.end_change()
        self.page_view.set_page(min(pages[0], self.doc.page_count - 1))
        self.status_label.setText("已删除 %d 页" % len(pages))

    def rotate_pages(self, pages, angle):
        pages = sorted(set(pages)) or [self.page_view.page_index]
        self.doc.begin_change("旋转页面")
        try:
            pageops.rotate_pages(self.doc, pages, angle)
        except Exception as exc:
            self.doc.undo()
            QtWidgets.QMessageBox.warning(self, "旋转失败", str(exc))
            return
        self.doc.end_change()
        self.page_view.refresh()
        self.status_label.setText("已旋转 %d 页（%d°）" % (len(pages), angle))

    def move_page_by(self, index, delta):
        self.move_page_to(index, index + delta)

    def reorder_pages(self, order):
        """缩略图拖拽后按新页序重排（order 是"新第 i 位放原来第几页"）。

        和右键菜单里的「上移/下移」共用同一条路：包撤销、刷新视图。
        拖拽本身不算文档修改（那只是界面动作），真正的改动在这里发生，
        所以撤销栈里只有一次「调整页序」。
        """
        if not self.doc.is_open:
            return
        total = self.doc.page_count
        if len(order) != total or sorted(order) != list(range(total)):
            return
        if order == list(range(total)):
            return
        # 拖拽前停在哪一页，拖完还停在哪一页的内容上（页号会变，内容不该跳）
        current = self.page_view.page_index
        new_current = order.index(current) if 0 <= current < total else 0
        self.doc.begin_change("调整页序")
        try:
            pageops.reorder_pages(self.doc, order)
        except PdfError as exc:
            self.doc.undo()   # 撤销栈里刚压进去的那一帧要退回来
            QtWidgets.QMessageBox.warning(self, "调整页序失败", str(exc))
            return
        self.doc.end_change()
        self.page_view.set_page(new_current)
        self.status_label.setText("页面顺序已调整")

    def move_page_to(self, index, target):
        total = self.doc.page_count
        if not (0 <= index < total):
            return
        target = max(0, min(target, total - 1))
        if target == index:
            return
        order = list(range(total))
        order.insert(target, order.pop(index))
        self.doc.begin_change("调整页序")
        try:
            pageops.reorder_pages(self.doc, order)
        except PdfError as exc:
            self.doc.undo()
            QtWidgets.QMessageBox.warning(self, "移动失败", str(exc))
            return
        self.doc.end_change()
        self.page_view.set_page(target)
        self.status_label.setText("页面已移动到第 %d 页" % (target + 1))

    def extract_selected(self, pages):
        pages = sorted(set(pages))
        if not pages:
            return
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "提取 %d 页另存为" % len(pages), "提取页面.pdf", "PDF 文件 (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            pageops.extract_pages(self.doc, pages, path)
        except PdfError as exc:
            QtWidgets.QMessageBox.warning(self, "提取失败", str(exc))
            return
        self.status_label.setText("已提取 %d 页到 %s" % (len(pages), path))

    def export_selected_images(self, pages):
        pages = sorted(set(pages))
        out_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "选择导出目录")
        if not out_dir:
            return
        try:
            files = self.doc.export_images(out_dir, pages=pages, dpi=150)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "导出失败", str(exc))
            return
        self.status_label.setText("已导出 %d 张图片" % len(files))

    def rotate(self, angle):
        self.rotate_pages([self.page_view.page_index], angle)

    def insert_from_file(self):
        path, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择要插入的 PDF", "", "PDF 文件 (*.pdf)")
        if not path:
            return
        try:
            source = fitz.open(path)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "无法打开", str(exc))
            return
        page_count = source.page_count
        source.close()
        dialog = dialogs.InsertFileDialog(path, page_count, self.page_view.page_index, self)
        if not dialog.exec_dialog():
            return
        values = dialog.values()
        from_page, to_page = _parse_page_range(values["ranges"], page_count)
        if from_page is None:
            QtWidgets.QMessageBox.warning(self, "页码有误", "请检查页码范围，例如 1-3 或 2,5。")
            return
        if values["position"] == "before":
            index = self.page_view.page_index
        elif values["position"] == "end":
            index = self.doc.page_count
        else:
            index = self.page_view.page_index + 1
        self.doc.begin_change("插入页面")
        try:
            pageops.insert_from_file(self.doc, path, index, from_page, to_page)
        except PdfError as exc:
            self.doc.undo()
            QtWidgets.QMessageBox.warning(self, "插入失败", str(exc))
            return
        self.doc.end_change()
        self.page_view.set_page(index)
        self.status_label.setText("已插入 %d 页" % (to_page - from_page + 1))

    def extract_pages(self):
        text, ok = QtWidgets.QInputDialog.getText(
            self, "提取页面", "要提取哪些页面？（例如 1-3,5，留空表示当前页）",
            QtWidgets.QLineEdit.Normal, str(self.page_view.page_index + 1))
        if not ok or not text.strip():
            return
        indices = _parse_indices(text, self.doc.page_count)
        if not indices:
            QtWidgets.QMessageBox.warning(self, "页码有误", "没有解析出有效页码。")
            return
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "保存提取的页面", "提取页面.pdf", "PDF 文件 (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            pageops.extract_pages(self.doc, indices, path)
        except PdfError as exc:
            QtWidgets.QMessageBox.warning(self, "提取失败", str(exc))
            return
        self.status_label.setText("已提取 %d 页到 %s" % (len(indices), path))

    def split_document(self):
        dialog = dialogs.SplitDialog(self, self.doc.page_count)
        if not dialog.exec_dialog():
            return
        values = dialog.values()
        out_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not out_dir:
            return
        try:
            if values["mode"] == "each":
                files = pageops.split_each_page(self.doc, out_dir)
            else:
                ranges = _parse_ranges(values["ranges"], self.doc.page_count)
                if not ranges:
                    QtWidgets.QMessageBox.warning(self, "页码有误", "请检查页码范围。")
                    return
                files = pageops.split_by_ranges(self.doc, out_dir, ranges)
        except PdfError as exc:
            QtWidgets.QMessageBox.warning(self, "拆分失败", str(exc))
            return
        self.status_label.setText("已拆分为 %d 个文件" % len(files))
        QtWidgets.QMessageBox.information(self, "拆分完成",
                                          "已生成 %d 个文件：\n%s" % (len(files), out_dir))

    def merge_into(self):
        paths, _filter = QtWidgets.QFileDialog.getOpenFileNames(
            self, "选择要合并的 PDF（可多选）", "", "PDF 文件 (*.pdf)")
        if not paths:
            return
        self.doc.begin_change("合并文档")
        try:
            for path in paths:
                pageops.insert_from_file(self.doc, path, self.doc.page_count)
        except PdfError as exc:
            self.doc.undo()
            QtWidgets.QMessageBox.warning(self, "合并失败", str(exc))
            return
        self.doc.end_change()
        self.status_label.setText("已合并 %d 个文件" % len(paths))

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    def add_watermark(self):
        dialog = dialogs.WatermarkDialog(self)
        if not dialog.exec_dialog():
            return
        values = dialog.values()
        if not values["text"]:
            QtWidgets.QMessageBox.warning(self, "缺少内容", "请输入水印文字。")
            return
        pages = None
        if values["scope"] == "current":
            pages = [self.page_view.page_index]
        self.doc.begin_change("添加水印")
        try:
            decorate.add_watermark(
                self.doc, values["text"], font_size=values["font_size"],
                color=values["color"], opacity=values["opacity"],
                angle=values["angle"], mode=values["mode"], pages=pages)
        except PdfError as exc:
            self.doc.undo()
            QtWidgets.QMessageBox.warning(self, "添加失败", str(exc))
            return
        self.doc.end_change()
        self.status_label.setText("水印已添加")

    def add_page_numbers(self):
        dialog = dialogs.PageNumberDialog(self)
        if not dialog.exec_dialog():
            return
        values = dialog.values()
        self.doc.begin_change("添加页码")
        try:
            decorate.add_page_numbers(self.doc, **values)
        except PdfError as exc:
            self.doc.undo()
            QtWidgets.QMessageBox.warning(self, "添加失败", str(exc))
            return
        self.doc.end_change()
        self.status_label.setText("页码已添加")

    def encrypt_document(self):
        dialog = dialogs.EncryptDialog(self)
        if not dialog.exec_dialog():
            return
        values = dialog.values()
        if not values["user_password"]:
            QtWidgets.QMessageBox.warning(self, "缺少密码", "请设置打开密码。")
            return
        if values["user_password"] != values["confirm"]:
            QtWidgets.QMessageBox.warning(self, "密码不一致", "两次输入的密码不一样。")
            return
        default = self.doc.path.replace(".pdf", "_加密.pdf") if self.doc.path else "加密文档.pdf"
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(self, "保存加密副本", default, "PDF 文件 (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            security.encrypt_to(
                self.doc, path, values["user_password"], values["owner_password"],
                values["allow_print"], values["allow_copy"], values["allow_modify"],
                values["allow_annotate"], True)
        except PdfError as exc:
            QtWidgets.QMessageBox.warning(self, "加密失败", str(exc))
            return
        self.status_label.setText("已保存加密副本：%s" % path)
        QtWidgets.QMessageBox.information(self, "加密完成", "加密副本已保存到：\n%s" % path)

    def decrypt_document(self):
        if self.doc.password:
            path, _filter = QtWidgets.QFileDialog.getSaveFileName(
                self, "保存无密码副本",
                self.doc.path.replace(".pdf", "_无密码.pdf"), "PDF 文件 (*.pdf)")
            if not path:
                return
            try:
                security.decrypt_to(self.doc, path)
            except PdfError as exc:
                QtWidgets.QMessageBox.warning(self, "失败", str(exc))
                return
            self.status_label.setText("已保存无密码副本")
            return
        QtWidgets.QMessageBox.information(self, "无需解密", "当前文档没有设置打开密码。")

    def redact_text(self):
        dialog = dialogs.RedactTextDialog(self)
        if not dialog.exec_dialog():
            return
        values = dialog.values()
        if not values["text"]:
            return
        pages = [self.page_view.page_index] if values["scope"] == "current" else None
        self.doc.begin_change("涂黑脱敏")
        try:
            if values["mode"] == "regex":
                count = security.redact_regex(self.doc, values["text"], pages)
            else:
                count = security.redact_text(self.doc, values["text"], pages)
        except PdfError as exc:
            self.doc.undo()
            QtWidgets.QMessageBox.warning(self, "涂黑失败", str(exc))
            return
        self.doc.end_change()
        self.status_label.setText("已涂黑 %d 处内容" % count)

    def fill_form(self):
        items = []
        for index in range(self.doc.page_count):
            for widget in self.doc.widgets(index):
                widget["page"] = index
                widget["key"] = "%d:%s" % (index, widget["name"])
                items.append(widget)
        if not items:
            QtWidgets.QMessageBox.information(self, "没有表单", "这个文档里没有可填写的表单字段。")
            return
        dialog = dialogs.FormFillDialog(items, self)
        if not dialog.exec_dialog():
            return
        values = dialog.values()
        self.doc.begin_change("填写表单")
        try:
            for index in range(self.doc.page_count):
                page = self.doc.doc[index]
                for widget in page.widgets() or []:
                    key = "%d:%s" % (index, widget.field_name)
                    if key in values:
                        widget.field_value = values[key]
                        widget.update()
        except Exception as exc:
            self.doc.undo()
            QtWidgets.QMessageBox.warning(self, "填写失败", str(exc))
            return
        self.doc.end_change()
        self.status_label.setText("表单已更新")

    def ocr_page(self):
        try:
            text = textops.ocr_page_text(self.doc.doc[self.page_view.page_index])
        except PdfError as exc:
            QtWidgets.QMessageBox.warning(self, "OCR 不可用", str(exc))
            return
        dialog = dialogs.TextInputDialog(
            "OCR 识别结果（第 %d 页）" % (self.page_view.page_index + 1),
            "识别出的文字如下，可以直接复制：", text, self, height=320)
        dialog.exec_dialog()

    def edit_metadata(self):
        dialog = dialogs.MetadataDialog(self.doc.metadata(), self)
        if not dialog.exec_dialog():
            return
        self.doc.begin_change("修改属性")
        self.doc.set_metadata(dialog.values())
        self.doc.end_change()
        self.status_label.setText("文档属性已更新")

    # ------------------------------------------------------------------
    # 导出 / 打印
    # ------------------------------------------------------------------
    def export_images(self):
        dialog = dialogs.ExportImageDialog(self)
        if not dialog.exec_dialog():
            return
        values = dialog.values()
        out_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "选择导出目录")
        if not out_dir:
            return
        pages = [self.page_view.page_index] if values["scope"] == "current" else None
        try:
            files = self.doc.export_images(out_dir, pages=pages, dpi=values["dpi"],
                                           fmt=values["format"])
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "导出失败", str(exc))
            return
        self.status_label.setText("已导出 %d 张图片" % len(files))

    def export_text(self):
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "导出文本", "文档文本.txt", "文本文件 (*.txt)")
        if not path:
            return
        try:
            self.doc.export_text(path)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "导出失败", str(exc))
            return
        self.status_label.setText("文本已导出到 %s" % path)

    def export_long_image(self):
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "导出长图", "文档长图.png", "PNG 图片 (*.png)")
        if not path:
            return
        try:
            export_mod.to_long_image(self.doc, path, dpi=110, gap=12)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "导出失败", str(exc))
            return
        self.status_label.setText("长图已导出到 %s" % path)

    def compress_document(self):
        size = export_mod.file_size(self.doc.path) if self.doc.path else 0
        dialog = dialogs.CompressDialog(self, size)
        if not dialog.exec_dialog():
            return
        values = dialog.values()
        default = (self.doc.path or "压缩.pdf").replace(".pdf", "_压缩.pdf")
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(self, "保存压缩副本", default, "PDF 文件 (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        self.status_label.setText("正在压缩，请稍候…")
        QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            export_mod.compress_to(self.doc, path, values["level"], values["dpi"], values["quality"])
        except PdfError as exc:
            QtWidgets.QApplication.restoreOverrideCursor()
            QtWidgets.QMessageBox.warning(self, "压缩失败", str(exc))
            return
        finally:
            if QtWidgets.QApplication.overrideCursor() is not None:
                QtWidgets.QApplication.restoreOverrideCursor()
        before = export_mod.human_size(size)
        after = export_mod.human_size(export_mod.file_size(path))
        self.status_label.setText("压缩完成：%s → %s" % (before, after))
        QtWidgets.QMessageBox.information(
            self, "压缩完成", "原文件：%s\n压缩后：%s\n\n保存位置：\n%s" % (before, after, path))

    def print_document(self):
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("打印文档")
        if qexec(dialog) != QtWidgets.QDialog.Accepted:
            return
        painter = QtGui.QPainter()
        if not painter.begin(printer):
            QtWidgets.QMessageBox.warning(self, "打印失败", "无法初始化打印机。")
            return
        try:
            dpi = printer.resolution() or 300
            for index in range(self.doc.page_count):
                if index:
                    printer.newPage()
                pix = self.doc.page_pixmap_for_print(index, dpi)
                image = QtGui.QImage(pix.samples, pix.width, pix.height, pix.stride, RGB888)
                viewport = painter.viewport()
                size = QtCore.QSizeF(image.width(), image.height())
                size.scale(QtCore.QSizeF(viewport.width(), viewport.height()),
                           Qt.KeepAspectRatio)
                x = (viewport.width() - size.width()) / 2.0
                y = (viewport.height() - size.height()) / 2.0
                painter.drawImage(QtCore.QRectF(x, y, size.width(), size.height()), image)
        finally:
            painter.end()
        self.status_label.setText("打印任务已发送")

    # ------------------------------------------------------------------
    # 其它
    # ------------------------------------------------------------------
    def _goto_annotation(self, page_index, xref):
        self.goto_page(page_index)
        self.page_view._selected_xref = xref
        self.page_view._selected_page = page_index
        self.page_view.update()

    def show_about(self):
        import pymupdf

        from ..qtcompat import QT_API
        version = getattr(pymupdf, "version", ("", "", ""))
        dialog = dialogs.AboutDialog(
            self, QT_API, version[0] if isinstance(version, (list, tuple)) else str(version))
        dialog.exec_dialog()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._on_escape()
            return
        QtWidgets.QMainWindow.keyPressEvent(self, event)


# ----------------------------------------------------------------------
# 页码文本解析
# ----------------------------------------------------------------------
def _parse_indices(text, page_count):
    out = []
    for part in text.replace("，", ",").replace("、", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            pieces = part.split("-", 1)
            try:
                start = int(pieces[0])
                end = int(pieces[1])
            except ValueError:
                continue
            for i in range(start, end + 1):
                if 1 <= i <= page_count and (i - 1) not in out:
                    out.append(i - 1)
        else:
            try:
                value = int(part)
            except ValueError:
                continue
            if 1 <= value <= page_count and (value - 1) not in out:
                out.append(value - 1)
    return sorted(out)


def _parse_ranges(text, page_count):
    ranges = []
    for part in text.replace("，", ",").replace("、", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            pieces = part.split("-", 1)
            try:
                start = int(pieces[0]) - 1
                end = int(pieces[1]) - 1
            except ValueError:
                continue
        else:
            try:
                start = end = int(part) - 1
            except ValueError:
                continue
        start = max(0, start)
        end = min(page_count - 1, end)
        if end >= start:
            ranges.append((start, end))
    return ranges


def _parse_page_range(text, page_count):
    ranges = _parse_ranges(text, page_count)
    if not ranges:
        return None, None
    return ranges[0][0], ranges[-1][1]
