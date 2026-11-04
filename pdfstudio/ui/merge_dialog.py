# -*- coding: utf-8 -*-
"""合并 PDF 对话框：把多个文件合成一个，缩略图直接拖拽调整顺序。

界面分三块：
    左  源文件清单（添加 / 移除，不参与排序）
    右  合并预览（每张缩略图就是输出里的一页，拖拽改顺序、Delete 删页）
    下  输出路径 + 开始合并

**页序只有一份真相**，就是 MergePlan.order。列表里的条目顺序永远跟着它走，
所以"拖拽 → 模型 → 写文件"这条链路中间没有第二套状态可以对不上。
"""

import os
from collections import deque

from ..qtcompat import QtCore, QtGui, QtWidgets, Qt, Signal, qexec

from ..core import merge as merge_mod
from ..core.document import PdfError

from . import icons
from .side_panel import render_page_pixmap, placeholder_pixmap, thumb_icon
from .theme import COLORS


# 合并窗口一屏要放更多页，缩略图比侧栏小一号；比例仍是 A4，避免格子忽高忽低。
# 格子只比图多 16px：多出来的部分当间距用，再叠加 setSpacing 就会白吃掉一列。
MERGE_THUMB_W = 100
MERGE_THUMB_H = 141
CELL_W = MERGE_THUMB_W + 16
CELL_H = MERGE_THUMB_H + 26


# QListWidget 内部拖拽用的 mime 类型。正常情况下靠 event.source() 判断"是不是
# 自己拖自己"，但个别平台/后端上 source() 会拿不到，多留一层判断，
# 免得又变成"有时候能拖有时候不能"。
INTERNAL_MIME = "application/x-qabstractitemmodeldatalist"


def pdf_paths_from(mime):
    """从拖拽数据里取出本地 PDF 路径。

    列表和对话框两处都要判，抽出来免得两边规则不一致——
    一边接受 .PDF 大写、另一边不接受，用户就会觉得"有时候能拖有时候不能"。
    """
    if not mime.hasUrls():
        return []
    paths = [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]
    return [path for path in paths if path.lower().endswith(".pdf")]


def drop_placement(count, moving, target):
    """算出拖拽落点：返回 (要搬的行号, 搬走之后插到第几行)。

    target 用"原始行号"表示插入点（等于 count 就是末尾）。搬走 k 行之后，
    插到目标位置的实际行号会前移"原本排在它前面的那些行"的数量。这里一次算清，
    否则"往前拖"和"往后拖"得写两套 ±1，很容易差一位。
    """
    moving = sorted(set(row for row in moving if 0 <= row < count))
    if not moving:
        return [], 0
    target = max(0, min(target, count))
    ahead = len([row for row in moving if row < target])
    at = max(0, min(target - ahead, count - len(moving)))
    return moving, at


def is_noop_move(moving, at):
    """要搬的行本来就在目标位置——别白搬一趟（白搬会把选中状态抖一下）。"""
    return moving == list(range(at, at + len(moving)))


class MergePageList(QtWidgets.QListWidget):
    """合并预览列表：InternalMove 拖拽 + 分批渲染。

    故意**不开** setUniformItemSizes(True)。主界面的缩略图列表用过那个开关，
    代价是"任何一条没有图标的条目都会把整列尺寸拖垮"。这里条目是动态增删的，
    而且拖拽过程中 Qt 会临时插入/删除行，一旦某一行 sizeHint 塌陷，
    整屏缩略图会一起变形。格子尺寸由 gridSize 固定住，逐条计算 sizeHint
    的开销在几十到几百页的量级完全可以接受。
    """

    orderChanged = Signal()
    filesDropped = Signal(list)
    deletePressed = Signal()
    dragFinished = Signal(str)   # 拖完给一句状态提示（空串表示正常搬动了）

    def __init__(self, parent=None):
        QtWidgets.QListWidget.__init__(self, parent)
        self.plan = None
        self._key_rows = {}   # (源, 页) -> 行号
        self._pending = deque()
        self._cache = {}      # (路径, 页) -> QPixmap
        self._drop_row = None  # 拖拽落点（插入位置），None 表示没在拖

        # 拖拽状态（自己实现，不走 QDrag）
        self._drag_start = None   # 按下时的鼠标位置，None 表示没在拖
        self._drag_key = None     # 按下时抓住的那一页 (源, 页)
        self._dragging = False    # 是否已越过拖拽阈值

        self.setViewMode(QtWidgets.QListView.IconMode)
        # IconMode 下 movement 必须是 Static，否则图标会被拖成自由摆放
        self.setMovement(QtWidgets.QListView.Static)
        self.setResizeMode(QtWidgets.QListView.Adjust)
        self.setWordWrap(True)
        self.setIconSize(QtCore.QSize(MERGE_THUMB_W, MERGE_THUMB_H))
        self.setGridSize(QtCore.QSize(CELL_W, CELL_H))
        self.setSpacing(0)
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

        # setDragEnabled(False) 是必须的，不是"保险"：
        # 内置拖拽会进 QDrag::exec() 这个平台级模态循环，实测在本机上进去
        # 出不来（松手没反应，看起来就是"拖不动"）。拖拽改由本类的
        # mousePress/mouseMove/mouseRelease 处理，见下面「拖拽」一节。
        self.setDragEnabled(False)
        self.setDragDropMode(QtWidgets.QAbstractItemView.NoDragDrop)
        # 仍然要接受"从文件管理器拖进来的 PDF"，那是另一套事件
        self.setAcceptDrops(True)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(12)
        self._timer.timeout.connect(self._render_next)

    # ------------------------------------------------------------------
    def set_plan(self, plan):
        """清空并重建。只在增删源文件这种结构性变化时调用。"""
        self.stop()
        self.plan = plan
        self._key_rows = {}
        self._pending.clear()
        self.clear()

    def add_page_item(self, key):
        item = QtWidgets.QListWidgetItem("")
        item.setIcon(thumb_icon(placeholder_pixmap(MERGE_THUMB_W, MERGE_THUMB_H)))
        item.setTextAlignment(Qt.AlignHCenter)
        item.setData(Qt.UserRole, key)
        self.addItem(item)
        self._pending.append(key)
        self._key_rows[key] = self.count() - 1
        if not self._timer.isActive():
            self._timer.start()

    def forget(self, key):
        """条目被删掉后，别再排队画它。"""
        try:
            self._pending.remove(key)
        except ValueError:
            pass
        self._key_rows.pop(key, None)

    def stop(self):
        self._timer.stop()
        self._pending.clear()
        self._drop_row = None

    def renumber(self):
        """按当前行号重排文字与来源提示，并重建 key -> 行号 映射。

        拖拽、删页、重建之后都要调一次，否则"第 N 页"会停在旧值上，
        用户看到的就是"拖了但编号没变"。
        """
        self._key_rows = {}
        for row in range(self.count()):
            item = self.item(row)
            key = item.data(Qt.UserRole)
            if key is None:
                continue
            self._key_rows[key] = row
            item.setText("第 %d 页" % (row + 1))
            item.setToolTip(self._tooltip_for(key))

    def _tooltip_for(self, key):
        source = self._source_of(key)
        if source is None:
            return ""
        return "%s\n原第 %d 页" % (source.path, key[1] + 1)

    def _source_of(self, key):
        if self.plan is None:
            return None
        index = key[0]
        if 0 <= index < len(self.plan.sources):
            return self.plan.sources[index]
        return None

    def current_keys(self):
        keys = []
        for row in range(self.count()):
            key = self.item(row).data(Qt.UserRole)
            if key is not None:
                keys.append(key)
        return keys

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------
    def _pixmap_for(self, key):
        source = self._source_of(key)
        if source is None:
            return None
        # 缓存按"文件路径 + 页码"存：源文件下标会因为移除文件而整体前移，
        # 用下标当 key 会导致移除一个文件后缩略图全画错页。
        cache_key = (source.path, key[1])
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            pm = render_page_pixmap(source.page(key[1]), MERGE_THUMB_W, MERGE_THUMB_H,
                                    background="#e9ecf2", border="#c2c8d4")
        except Exception:
            return None
        if len(self._cache) > 500:
            self._cache.clear()
        self._cache[cache_key] = pm
        return pm

    def _pick_next(self):
        """可见区优先：几百页的文件里，先画屏幕上看得见的那几张。"""
        if not self._pending:
            return None
        view = self.viewport().rect()
        for key in self._pending:
            row = self._key_rows.get(key)
            if row is None or row >= self.count():
                continue
            if view.intersects(self.visualItemRect(self.item(row))):
                return key
        return self._pending[0]

    def _render_next(self):
        if self.plan is None or not self._pending:
            self._timer.stop()
            return
        key = self._pick_next()
        if key is None:
            self._timer.stop()
            return
        try:
            self._pending.remove(key)
        except ValueError:
            return
        row = self._key_rows.get(key)
        if row is None or row >= self.count():
            return
        item = self.item(row)
        if item is None:
            return
        if item.data(Qt.UserRole) != key:
            # 行号对不上了（刚拖完还没重编号），重建映射后本轮跳过
            self.renumber()
            return
        pm = self._pixmap_for(key)
        if pm is not None:
            item.setIcon(thumb_icon(pm))

    # ------------------------------------------------------------------
    # 拖拽
    # ------------------------------------------------------------------
    def _is_page_drag(self, event):
        """这次拖拽是不是"列表里的页在挪位置"，而不是拖进来一个文件。"""
        if event.source() is self:
            return True
        mime = event.mimeData()
        return mime is not None and mime.hasFormat(INTERNAL_MIME)

    def dragEnterEvent(self, event):
        # 只接受 PDF 和自己拖自己。拖别的文件进来时让鼠标显示"禁止"，
        # 比"能放但放下去没反应"清楚得多。
        if pdf_paths_from(event.mimeData()) or self._is_page_drag(event):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if pdf_paths_from(event.mimeData()):
            event.acceptProposedAction()
            return
        if self._is_page_drag(event):
            # 本列表内部的拖拽已经不吃这条路径了（见下面的鼠标实现），
            # 这里只兜"从别的控件拖过来"的情况。
            QtWidgets.QListWidget.dragMoveEvent(self, event)
            self._drop_row = self._drop_target(event.pos())
            self.viewport().update()
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._drop_row = None
        self.viewport().update()
        QtWidgets.QListWidget.dragLeaveEvent(self, event)

    def dropEvent(self, event):
        paths = pdf_paths_from(event.mimeData())
        if paths:
            # 列表自己吃掉这个事件：否则 Qt 会往上找父窗口，
            # 落点稍微偏一点就没反应。
            event.acceptProposedAction()
            self.filesDropped.emit(paths)
            return
        if not self._is_page_drag(event):
            event.ignore()
            return
        rows = sorted(set(index.row() for index in self.selectedIndexes()))
        self._drop_row = None
        self.apply_drop(rows, self._drop_target(event.pos()))
        if event.possibleActions() & Qt.CopyAction:
            event.setDropAction(Qt.CopyAction)
        else:
            self.clearSelection()
            self.setCurrentRow(-1)
        event.accept()

    # ------------------------------------------------------------------
    # 内置拖拽（QDrag）为什么被停用
    # ------------------------------------------------------------------
    # QListView 的拖拽要走 QDrag::exec()，那是一个**平台级模态循环**。
    # 实测（探针脚本 _probe_drag*.py）：startDrag 确实被调用，但 exec 进去
    # 之后松手没有任何响应，进程停在模态循环里出不来——现象正是用户说的
    # "鼠标拖拽还是没能成功"。更麻烦的是这个模态循环自动化测试进不去，
    # 测试只能覆盖 exec 之外的代码，于是"改完测试全绿、用户还是拖不动"
    # 连着发生了两轮。
    #
    # 现在按下/移动/松手全在本类里处理：没有模态循环、没有平台差异，
    # 测试可以用真实鼠标事件把整条链路完整驱动一遍。
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            index = self.indexAt(event.pos())
            if index.isValid():
                self._drag_start = event.pos()
                self._drag_key = self.item(index.row()).data(Qt.UserRole)
                self._dragging = False
        QtWidgets.QListWidget.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        if self._drag_start is None or not (event.buttons() & Qt.LeftButton):
            QtWidgets.QListWidget.mouseMoveEvent(self, event)
            return
        if not self._dragging:
            moved = (event.pos() - self._drag_start).manhattanLength()
            if moved < QtWidgets.QApplication.startDragDistance():
                QtWidgets.QListWidget.mouseMoveEvent(self, event)
                return
            # 越过阈值才算拖拽：不然轻轻一点就搬了页，非常容易误操作
            self._dragging = True
        self._drop_row = self._drop_target(event.pos())
        self.viewport().update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            target = self._drop_target(event.pos())
            rows = sorted(set(index.row() for index in self.selectedIndexes()))
            if not rows and self._drag_key is not None:
                row = self._key_rows.get(self._drag_key)
                if row is not None:
                    rows = [row]
            self._reset_drag()
            event.accept()
            self._finish_drag(rows, target)
            return
        self._reset_drag()
        QtWidgets.QListWidget.mouseReleaseEvent(self, event)

    def _reset_drag(self):
        self._drag_start = None
        self._drag_key = None
        self._dragging = False
        self._drop_row = None
        self.viewport().update()

    def _finish_drag(self, rows, target):
        """松手：真的搬行；没搬动时给出提示。

        拖回原地（或只挪半格）时什么都不发生，用户看到的就是"拖不动"。
        这里补一条状态提示，把"系统确实识别到这次拖拽了"说清楚，
        免得把"没动"误判成"功能坏了"。
        """
        if not rows:
            return
        if self.apply_drop(rows, target):
            self.dragFinished.emit(u"")
        else:
            self.dragFinished.emit(u"拖到同一位置，顺序没有变化")

    def _drop_target(self, pos):
        """光标落在哪个插入位置（行号，count 表示末尾）。"""
        index = self.indexAt(pos)
        if not index.isValid():
            return self.count()
        rect = self.visualRect(index)
        row = index.row()
        # 落点在格子的"后半"就算插到它后面，否则插到它前面。
        # 只比上下会让同一行里左右方向的拖拽完全没反应，所以两个方向都看。
        if pos.y() > rect.center().y() or pos.x() > rect.center().x():
            return row + 1
        return row

    def apply_drop(self, rows, target):
        """把 rows 这些行搬到 target 位置，返回是否真的动了。"""
        moving, at = drop_placement(self.count(), rows, target)
        if not moving or is_noop_move(moving, at):
            return False
        items = []
        for row in reversed(moving):   # 从后往前取，前面的行号才不会失效
            items.append(self.takeItem(row))
        items.reverse()
        for offset, item in enumerate(items):
            self.insertItem(at + offset, item)
        # 搬完保持选中，方便接着调；否则每拖一次都要重新点一遍
        self.clearSelection()
        for offset in range(len(items)):
            self.item(at + offset).setSelected(True)
        self.after_drop()
        return True

    def after_drop(self):
        """搬完行之后的收尾：重编号 + 通知对话框同步模型。"""
        self.renumber()
        self.orderChanged.emit()

    def paintEvent(self, event):
        QtWidgets.QListWidget.paintEvent(self, event)
        if self._drop_row is not None:
            self._paint_drop_marker()

    def _paint_drop_marker(self):
        """画拖拽落点。

        IconMode 下 Qt 不画落点指示线（那是 ListMode 才有的行为），
        setDropIndicatorShown(True) 在图标模式里等于没开。拖的时候一点反馈都没有，
        用户会以为"拖不动"，所以这里自己画一条竖线。
        """
        if self.count() == 0:
            return
        row = self._drop_row
        if row < self.count():
            rect = self.visualItemRect(self.item(row))
            x = rect.left() - 4
        else:
            rect = self.visualItemRect(self.item(self.count() - 1))
            x = rect.right() + 4
        painter = QtGui.QPainter(self.viewport())
        painter.setPen(QtGui.QPen(QtGui.QColor(COLORS["primary"]), 3))
        painter.drawLine(x, rect.top(), x, rect.bottom())
        painter.end()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            # 交给对话框统一处理：删页要同时改模型和列表，
            # 列表自己删会让 plan.order 和界面上的顺序对不上
            self.deletePressed.emit()
            return
        QtWidgets.QListWidget.keyPressEvent(self, event)


class MergeDialog(QtWidgets.QDialog):
    """合并多个 PDF 为一个文件。"""

    def __init__(self, parent=None, paths=None, default_dir=None):
        QtWidgets.QDialog.__init__(self, parent)
        self.plan = merge_mod.MergePlan()
        self._out_path = ""
        self._out_touched = False
        self._merging = False
        self._default_dir = default_dir or os.path.expanduser("~")

        self.setWindowTitle("合并 PDF 文件")
        self.setModal(True)
        self.setAcceptDrops(True)
        self.setWindowIcon(QtGui.QIcon(icons.app_icon(64)))
        self.resize(1180, 760)
        self.setMinimumSize(820, 560)

        self._build()
        if paths:
            self.add_paths(paths)
        self._refresh_all()

    # ------------------------------------------------------------------
    # 界面
    # ------------------------------------------------------------------
    def _build(self):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(12)

        title = QtWidgets.QLabel("合并 PDF 文件")
        font = title.font()
        font.setPointSize(font.pointSize() + 3)
        font.setBold(True)
        title.setFont(font)
        outer.addWidget(title)

        hint = QtWidgets.QLabel(
            "拖动缩略图调整顺序，选中后按 Delete 删掉不要的页；"
            "也可以把 PDF 从文件夹里直接拖进这个窗口。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: %s; font-size: 12px;" % COLORS["text_sub"])
        outer.addWidget(hint)

        splitter = QtWidgets.QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_source_panel())
        splitter.addWidget(self._build_preview_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([290, 860])
        outer.addWidget(splitter, 1)

        outer.addLayout(self._build_output_row())

        buttons = QtWidgets.QDialogButtonBox()
        self.btn_ok = buttons.addButton("开始合并", QtWidgets.QDialogButtonBox.AcceptRole)
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.run_merge)
        self.btn_cancel = buttons.addButton("取消", QtWidgets.QDialogButtonBox.RejectRole)
        self.btn_cancel.clicked.connect(self.reject)
        outer.addWidget(buttons)

    def _build_source_panel(self):
        box = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(8)

        head = QtWidgets.QHBoxLayout()
        head.setSpacing(6)
        label = QtWidgets.QLabel("源文件")
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        head.addWidget(label)
        head.addStretch(1)

        self.btn_add = QtWidgets.QToolButton()
        self.btn_add.setText("添加")
        self.btn_add.setIcon(icons.icon("plus", 16))
        self.btn_add.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_add.setToolTip("添加 PDF 文件（可多选）")
        self.btn_add.clicked.connect(self.choose_files)
        head.addWidget(self.btn_add)

        self.btn_remove = QtWidgets.QToolButton()
        self.btn_remove.setText("移除")
        self.btn_remove.setIcon(icons.icon("trash", 16))
        self.btn_remove.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_remove.setToolTip("把这个文件的所有页面从合并结果里去掉")
        self.btn_remove.clicked.connect(self.remove_current_source)
        head.addWidget(self.btn_remove)
        layout.addLayout(head)

        self.src_list = QtWidgets.QListWidget()
        self.src_list.setAlternatingRowColors(True)
        self.src_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.src_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.src_list.customContextMenuRequested.connect(self._source_menu)
        layout.addWidget(self.src_list, 1)

        tip = QtWidgets.QLabel("这里只管「有哪些文件」，顺序请在右边拖。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: %s; font-size: 11px;" % COLORS["text_sub"])
        layout.addWidget(tip)
        return box

    def _build_preview_panel(self):
        box = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(box)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(8)

        head = QtWidgets.QHBoxLayout()
        head.setSpacing(8)
        label = QtWidgets.QLabel("合并预览")
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        head.addWidget(label)

        self.count_label = QtWidgets.QLabel("0 个文件 · 共 0 页")
        self.count_label.setStyleSheet("color: %s;" % COLORS["text_sub"])
        head.addWidget(self.count_label)
        head.addStretch(1)

        self.btn_delete = QtWidgets.QToolButton()
        self.btn_delete.setText("删除所选")
        self.btn_delete.setIcon(icons.icon("trash", 16))
        self.btn_delete.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_delete.setToolTip("删除选中的页面（Delete 键同效）")
        self.btn_delete.clicked.connect(self.delete_selected)
        head.addWidget(self.btn_delete)

        self.btn_clear = QtWidgets.QToolButton()
        self.btn_clear.setText("全部清空")
        self.btn_clear.setToolTip("清空所有文件，重新开始")
        self.btn_clear.clicked.connect(self.clear_all)
        head.addWidget(self.btn_clear)
        layout.addLayout(head)

        self.page_list = MergePageList()
        self.page_list.set_plan(self.plan)
        self.page_list.orderChanged.connect(self._on_order_changed)
        self.page_list.filesDropped.connect(self.add_paths)
        self.page_list.deletePressed.connect(self.delete_selected)
        self.page_list.dragFinished.connect(self._on_drag_finished)
        layout.addWidget(self.page_list, 1)
        return box

    def _on_drag_finished(self, message):
        """拖拽结束的反馈。

        拖回原地时顺序本来就不该变，但如果不给任何提示，用户只会看到
        "拖了没反应"，分不清是没识别到拖拽还是拖对了位置。
        """
        if message:
            self.count_label.setText(message)
        else:
            self._refresh_summary()

    def _build_output_row(self):
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)
        label = QtWidgets.QLabel("保存为")
        row.addWidget(label)

        self.out_edit = QtWidgets.QLineEdit()
        self.out_edit.setPlaceholderText("合并结果的保存位置")
        self.out_edit.textEdited.connect(self._on_out_edited)
        row.addWidget(self.out_edit, 1)

        btn = QtWidgets.QToolButton()
        btn.setText("浏览…")
        btn.clicked.connect(self.choose_output)
        row.addWidget(btn)
        return row

    # ------------------------------------------------------------------
    # 状态刷新
    # ------------------------------------------------------------------
    def _refresh_all(self):
        self._refresh_source_list()
        self._refresh_summary()
        self._suggest_output()

    def _refresh_summary(self):
        total = self.plan.total_pages
        self.count_label.setText("%d 个文件 · 共 %d 页" % (self.plan.file_count, total))
        self.btn_ok.setEnabled(total > 0)
        self.btn_clear.setEnabled(total > 0)
        self.btn_delete.setEnabled(total > 0)

    def _refresh_source_list(self):
        current = self.src_list.currentRow()
        self.src_list.clear()
        for index, source in enumerate(self.plan.sources):
            kept = self.plan.kept_pages(index)
            if kept == source.page_count:
                detail = "%d 页" % source.page_count
            else:
                detail = "%d / %d 页" % (kept, source.page_count)
            item = QtWidgets.QListWidgetItem(icons.icon("doc", 16),
                                             "%s   %s" % (source.name, detail))
            item.setToolTip(source.path)
            item.setData(Qt.UserRole, index)
            self.src_list.addItem(item)
        if self.plan.sources:
            row = current if 0 <= current < self.src_list.count() else 0
            self.src_list.setCurrentRow(row)

    def _suggest_output(self):
        if self._out_touched or not self.plan.sources:
            return
        # 存在第一个源文件旁边最顺手：用户合并完通常就在那个文件夹里用
        folder = os.path.dirname(self.plan.sources[0].path) or self._default_dir
        self.out_edit.setText(
            merge_mod.default_output_name(self.plan.sources, folder))

    def _on_out_edited(self, _text):
        self._out_touched = True

    def _on_order_changed(self):
        try:
            self.plan.set_order(self.page_list.current_keys())
        except PdfError:
            # 界面和模型脱节了，重建一次，别带着错状态继续
            self._rebuild_preview()
            return
        self._refresh_summary()

    def _rebuild_preview(self):
        """按 plan.order 重建整个预览列表。

        只在"移除源文件"这种会改变源下标的情况下用：plan 里后面的源下标
        整体前移了，旧条目的 (源, 页) 已经指向错的文件，必须重挂。
        缩略图走缓存，重建是瞬时的。
        """
        self.page_list.set_plan(self.plan)
        for key in self.plan.order:
            self.page_list.add_page_item(key)
        self.page_list.renumber()

    # ------------------------------------------------------------------
    # 添加 / 移除
    # ------------------------------------------------------------------
    def choose_files(self):
        paths, _filter = QtWidgets.QFileDialog.getOpenFileNames(
            self, "选择要合并的 PDF（可多选）", self._default_dir,
            "PDF 文件 (*.pdf);;所有文件 (*)")
        if paths:
            self.add_paths(paths)

    def add_paths(self, paths):
        # 自然排序：用户一次选十几份分卷文件时，字典序会排出
        # 1, 10, 11, 2 这种明显不对的顺序
        candidates = merge_mod.sort_paths(
            [p for p in paths if p.lower().endswith(".pdf")])
        if not candidates:
            return
        added = 0
        errors = []
        for path in candidates:
            try:
                index = self._add_one(path)
            except PdfError as exc:
                errors.append(str(exc))
                continue
            if index is None:
                continue
            self._append_source(index)
            added += 1
        if added:
            self._refresh_all()
            self.page_list.renumber()
        if errors:
            QtWidgets.QMessageBox.warning(
                self, "有些文件没能加入",
                "下列文件被跳过了：\n\n%s" % "\n".join(errors[:8]))
        elif not added and candidates:
            self._refresh_summary()

    def _add_one(self, path, password=""):
        """加入一个文件；需要密码时问一次再重试。返回源下标或 None。"""
        try:
            return self.plan.add_source(path, password)
        except PdfError as exc:
            if exc.code != "password":
                raise
            pwd, ok = QtWidgets.QInputDialog.getText(
                self, "需要密码",
                "《%s》已加密，请输入打开密码：" % os.path.basename(path),
                QtWidgets.QLineEdit.Password)
            if not ok or not pwd:
                return None
            return self._add_one(path, pwd)

    def _append_source(self, index):
        source = self.plan.sources[index]
        for page in range(source.page_count):
            self.page_list.add_page_item((index, page))

    def remove_current_source(self):
        row = self.src_list.currentRow()
        if not (0 <= row < len(self.plan.sources)):
            return
        source = self.plan.sources[row]
        answer = QtWidgets.QMessageBox.question(
            self, "移除文件",
            "把《%s》的 %d 页从合并结果里去掉？\n\n"
            "文件本身不会被删除，只是不参与这次合并。" % (source.name, source.page_count),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No)
        if answer != QtWidgets.QMessageBox.Yes:
            return
        self.plan.remove_source(row)
        self._rebuild_preview()
        self._refresh_all()

    def _source_menu(self, pos):
        item = self.src_list.itemAt(pos)
        if item is None:
            return
        self.src_list.setCurrentItem(item)
        menu = QtWidgets.QMenu(self)
        menu.addAction("移除这个文件", self.remove_current_source)
        menu.addAction("打开文件所在目录", self._reveal_current)
        trigger = getattr(menu, "exec", None) or getattr(menu, "exec_")
        trigger(self.src_list.viewport().mapToGlobal(pos))

    def _reveal_current(self):
        row = self.src_list.currentRow()
        if not (0 <= row < len(self.plan.sources)):
            return
        folder = os.path.dirname(self.plan.sources[row].path)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(folder))

    # ------------------------------------------------------------------
    # 页序
    # ------------------------------------------------------------------
    def delete_selected(self):
        rows = sorted({self.page_list.row(item)
                       for item in self.page_list.selectedItems()})
        if not rows:
            QtWidgets.QMessageBox.information(
                self, "没有选中页面", "先在预览里点选要删除的页面（可以按住 Ctrl 多选）。")
            return
        if len(rows) >= self.plan.total_pages:
            QtWidgets.QMessageBox.information(
                self, "无法删除", "合并结果至少要保留一页。")
            return
        self.plan.drop_pages(rows)
        for row in sorted(rows, reverse=True):
            item = self.page_list.item(row)
            key = item.data(Qt.UserRole)
            self.page_list.takeItem(row)
            self.page_list.forget(key)
        self.page_list.renumber()
        self._refresh_source_list()
        self._refresh_summary()

    def clear_all(self):
        if not self.plan.total_pages:
            return
        answer = QtWidgets.QMessageBox.question(
            self, "清空", "把所有文件都从合并列表里去掉？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No)
        if answer != QtWidgets.QMessageBox.Yes:
            return
        self.plan.clear()
        self._rebuild_preview()
        self._out_touched = False
        self._refresh_all()

    # ------------------------------------------------------------------
    # 输出
    # ------------------------------------------------------------------
    def output_path(self):
        text = self.out_edit.text().strip()
        if not text:
            return ""
        if not text.lower().endswith(".pdf"):
            text += ".pdf"
        return text

    def choose_output(self):
        start = self.output_path() or merge_mod.default_output_name(
            self.plan.sources, self._default_dir)
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "合并结果保存为", start, "PDF 文件 (*.pdf)")
        if path:
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            self.out_edit.setText(path)
            self._out_touched = True

    def run_merge(self):
        if not self.plan.total_pages:
            return
        path = self.output_path()
        if not path:
            QtWidgets.QMessageBox.warning(
                self, "还没有保存位置", "请先点「浏览…」选择合并结果存到哪里。")
            return
        folder = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(folder):
            QtWidgets.QMessageBox.warning(
                self, "目录不存在", "这个目录不存在：\n%s" % folder)
            return
        if os.path.exists(path):
            answer = QtWidgets.QMessageBox.question(
                self, "文件已存在",
                "《%s》已经存在，要覆盖吗？" % os.path.basename(path),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No)
            if answer != QtWidgets.QMessageBox.Yes:
                return

        total = self.plan.total_pages
        progress = QtWidgets.QProgressDialog(
            "正在合并 %d 页…" % total, "", 0, total, self)
        progress.setWindowTitle("合并中")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.setValue(0)

        def report(done, _total):
            progress.setValue(done)
            QtWidgets.QApplication.processEvents()

        try:
            self._merging = True
            self.plan.build(path, report)
        except PdfError as exc:
            progress.close()
            QtWidgets.QMessageBox.warning(self, "合并失败", str(exc))
            return
        finally:
            self._merging = False
            progress.close()

        self._out_path = path
        self.accept()

    # ------------------------------------------------------------------
    # 其它
    # ------------------------------------------------------------------
    def result_path(self):
        """合并成功后的文件路径；取消时是空串。"""
        return self._out_path

    def exec_dialog(self):
        return qexec(self) == QtWidgets.QDialog.Accepted

    def dragEnterEvent(self, event):
        if pdf_paths_from(event.mimeData()):
            event.acceptProposedAction()
            return
        QtWidgets.QDialog.dragEnterEvent(self, event)

    def dropEvent(self, event):
        paths = pdf_paths_from(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self.add_paths(paths)
            return
        QtWidgets.QDialog.dropEvent(self, event)

    def done(self, result):
        # 合并途中用户点关闭（X）会让 done() 先跑，源文件句柄被放掉，
        # build() 里再去取页面就崩了。这里直接拒绝。
        if self._merging and result == QtWidgets.QDialog.Rejected:
            return
        # 先把文件句柄放掉再关窗，Windows 上留着句柄会让源文件"被占用"
        self.page_list.stop()
        self.plan.close()
        QtWidgets.QDialog.done(self, result)
