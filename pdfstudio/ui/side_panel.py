# -*- coding: utf-8 -*-
"""左侧面板：页面缩略图、目录、注释列表。"""

from ..qtcompat import QtCore, QtGui, QtWidgets, Qt, Signal, RGB888

from . import icons
from .theme import COLORS

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz


THUMB_WIDTH = 118
# 画布固定成 A4 比例。缩略图必须先铺到这块固定画布上再交给列表，
# 否则页面长宽比一变（长条页、横向表格页），图标尺寸就跟着变，
# 格子被迫变高、间距忽大忽小，图还会被二次缩放得像裁掉了上下。
THUMB_HEIGHT = 167


def placeholder_pixmap(width=THUMB_WIDTH, height=THUMB_HEIGHT, color="#f3f4f7"):
    pm = QtGui.QPixmap(width, height)
    pm.fill(QtGui.QColor(color))
    return pm


def render_page_pixmap(page, width=THUMB_WIDTH, height=THUMB_HEIGHT,
                       background="#f3f4f7", border=None):
    """把一页画成固定尺寸的缩略图，比例不符的地方留白。

    只按宽度算缩放是不够的：公文里常混着长条页、横向表格页，
    算出来的图可能比格子高、也可能比格子扁，Qt 会再缩放一次，
    结果是格子尺寸跟着页面比例变、缩略图看着像被裁了上下。

    尺寸做成参数，合并窗口要用小一号的画布（一屏要放更多页），
    但缩放逻辑必须是同一份，否则两处缩略图的观感对不上。

    border 给页面描一圈细线。绝大多数页面是白底，落在浅灰画布上
    边界根本看不出来，一屏几十个缩略图时很难分辨"哪张图对应哪个页码"。
    """
    rect = page.rect
    page_w = float(rect.width) or 595.0
    page_h = float(rect.height) or 842.0
    scale = min(width / page_w, height / page_h)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    image = QtGui.QImage(pix.samples, pix.width, pix.height, pix.stride, RGB888)
    page_pm = QtGui.QPixmap.fromImage(image)

    canvas = QtGui.QPixmap(width, height)
    canvas.fill(QtGui.QColor(background))
    painter = QtGui.QPainter(canvas)
    x = (width - page_pm.width()) // 2
    y = (height - page_pm.height()) // 2
    painter.drawPixmap(x, y, page_pm)
    if border:
        painter.setPen(QtGui.QPen(QtGui.QColor(border), 1))
        painter.drawRect(x, y, page_pm.width() - 1, page_pm.height() - 1)
    painter.end()
    return canvas


def thumb_icon(pixmap):
    """构造不被选中态染色的 QIcon。

    如果只给 Normal 态，Qt 会在选中时用高亮色给图标重新着色，
    缩略图会整块发蓝，这里把各状态都指向同一张图。
    """
    icon = QtGui.QIcon()
    for mode in (QtGui.QIcon.Normal, QtGui.QIcon.Active, QtGui.QIcon.Selected, QtGui.QIcon.Disabled):
        icon.addPixmap(pixmap, mode, QtGui.QIcon.Off)
        icon.addPixmap(pixmap, mode, QtGui.QIcon.On)
    return icon


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


def reorder_indices(count, moving, at):
    """把"搬哪几行、插到第几行"翻译成整套页序 [旧页号...]。

    返回值是"新顺序第 i 位放原来第几页"，可以直接交给 doc.select()。
    做成纯函数，测试不碰界面就能验证落点算没算错。
    """
    order = [i for i in range(count) if i not in moving]
    for offset, row in enumerate(moving):
        order.insert(min(at + offset, len(order)), row)
    return order


class ThumbnailList(QtWidgets.QListWidget):
    """缩略图列表：先占位，再用定时器分批渲染，打开大文件也不会卡住。

    支持 Ctrl / Shift 多选，右键弹出页面管理菜单（插入、删除、旋转、移动、提取）。
    """

    pageActivated = Signal(int)
    contextRequested = Signal(list, QtCore.QPoint)
    # 拖拽结束：参数是"新顺序"（新顺序第 i 位放原来第几页）；没搬动时给空列表
    pagesReordered = Signal(list)

    def __init__(self, parent=None):
        QtWidgets.QListWidget.__init__(self, parent)
        self.doc = None
        self.setViewMode(QtWidgets.QListView.IconMode)
        self.setMovement(QtWidgets.QListView.Static)
        self.setResizeMode(QtWidgets.QListView.Adjust)
        self.setWordWrap(True)
        self.setIconSize(QtCore.QSize(THUMB_WIDTH, THUMB_HEIGHT))
        self.setGridSize(QtCore.QSize(THUMB_WIDTH + 26, THUMB_HEIGHT + 34))
        self.setSpacing(4)
        self.setUniformItemSizes(True)
        self.setToolTip("按住缩略图拖动可以直接调整页序，右键有更多页面操作")
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self._pending = []
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(12)
        self._timer.timeout.connect(self._render_next)
        self.currentRowChanged.connect(self._on_row_changed)
        self._suppress = False

        # 拖拽整页排序。**不用 Qt 内置拖拽**：它要走 QDrag::exec()——平台级
        # 模态循环，实测在本机上进去出不来（松手没反应），而且自动化测试
        # 进不去那个循环，等于永远测不到。这里自己处理按下/移动/松手。
        self.setDragEnabled(False)
        self.setDragDropMode(QtWidgets.QAbstractItemView.NoDragDrop)
        self._drag_start = None   # 按下位置，None 表示没在拖
        self._drag_row = None     # 按下时抓住的那一页（在空白处按下时为 None）
        self._drag_mode = 0       # 见下面 _DRAG_* ：按在页上是排序，按在空白处是框选
        self._dragging = False    # 是否已判定为"拖整页"
        self._drop_row = None     # 当前落点（插入位置），用于画提示线
        self._band_rect = None    # 框选矩形，None 表示没在框选
        self._band_base = []      # 框选开始前已经选中的条目（Ctrl 框选时保留）

    def set_document(self, doc):
        self._timer.stop()
        self._pending = []
        # 重建列表的过程中会触发 currentRowChanged，必须整体屏蔽，
        # 否则清空列表时会把"当前页"误切换到别的页。
        self._suppress = True
        try:
            self.clear()
            self.doc = doc
            if doc is None or not doc.is_open:
                return
            placeholder = thumb_icon(placeholder_pixmap())
            for index in range(doc.page_count):
                item = QtWidgets.QListWidgetItem("第 %d 页" % (index + 1))
                item.setIcon(placeholder)
                item.setTextAlignment(Qt.AlignHCenter)
                item.setData(Qt.UserRole, index)
                self.addItem(item)
                self._pending.append(index)
            if self.count():
                self.setCurrentRow(0)
        finally:
            self._suppress = False
        self._timer.start()

    def refresh_all(self):
        if self.doc is None or not self.doc.is_open:
            return
        self._suppress = True
        try:
            current = self.currentRow()
            # 从当前页往外扩散，配合 _pick_next 的"可见优先"，
            # 用户眼睛附近的那几页总是最先画出来。
            anchor = current if current >= 0 else 0
            self._pending = sorted(range(self.doc.page_count),
                                   key=lambda i: abs(i - anchor))
            while self.count() > self.doc.page_count:
                self.takeItem(self.count() - 1)
            # 新增的条目也必须先挂占位图。
            # 没有图标的条目 sizeHint 只有几十像素，在 setUniformItemSizes(True)
            # 下会被当成统一尺寸，导致整列缩略图一起缩成一条、点都点不中。
            placeholder = thumb_icon(placeholder_pixmap())
            while self.count() < self.doc.page_count:
                index = self.count()
                item = QtWidgets.QListWidgetItem("第 %d 页" % (index + 1))
                item.setIcon(placeholder)
                item.setTextAlignment(Qt.AlignHCenter)
                item.setData(Qt.UserRole, index)
                self.addItem(item)
            for index in range(self.doc.page_count):
                self.item(index).setData(Qt.UserRole, index)
            if 0 <= current < self.count():
                self.setCurrentRow(current)
        finally:
            self._suppress = False
        # 条目数变了要重排一次，否则旧的格子尺寸会沿用下来
        self.doItemsLayout()
        self._timer.start()

    def selected_pages(self):
        pages = []
        for item in self.selectedItems():
            data = item.data(Qt.UserRole)
            if data is not None:
                pages.append(int(data))
        if not pages and self.currentItem() is not None:
            data = self.currentItem().data(Qt.UserRole)
            if data is not None:
                pages.append(int(data))
        return sorted(set(pages))

    def _on_context_menu(self, pos):
        item = self.itemAt(pos)
        if item is not None and not item.isSelected():
            self.clearSelection()
            item.setSelected(True)
            self.setCurrentItem(item)
        pages = self.selected_pages()
        if not pages and self.doc is not None and self.doc.is_open:
            pages = [0]
        self.contextRequested.emit(pages, self.viewport().mapToGlobal(pos))

    def set_current_page(self, index):
        if 0 <= index < self.count() and self.currentRow() != index:
            self._suppress = True
            try:
                self.setCurrentRow(index)
            finally:
                self._suppress = False

    def _on_row_changed(self, row):
        if self._suppress or row < 0 or self.doc is None:
            return
        self.pageActivated.emit(row)

    def _pick_next(self):
        """挑下一个要画的条目：优先画屏幕上看得见的。

        缩略图是一张一张画的，按顺序画的话页数一多就要好几秒；
        用户滚到第 300 页时只看到一片灰块，看起来就像"缩略图坏了"。
        先画可见区，滚到哪里哪里就先出图，顺序反而是次要的。
        """
        if not self._pending:
            return None
        view = self.viewport().rect()
        for index in self._pending:
            item = self.item(index)
            if item is None:
                continue
            if view.intersects(self.visualItemRect(item)):
                return index
        return self._pending[0]

    def _render_next(self):
        if self.doc is None or not self.doc.is_open:
            self._timer.stop()
            return
        index = self._pick_next()
        if index is None:
            self._timer.stop()
            return
        try:
            self._pending.remove(index)
        except ValueError:
            return
        if index >= self.doc.page_count or index >= self.count():
            return
        try:
            pm = render_page_pixmap(self.doc.doc[index])
        except Exception:
            pm = placeholder_pixmap()
        item = self.item(index)
        if item is not None:
            item.setIcon(thumb_icon(pm))

    # ------------------------------------------------------------------
    # 拖拽排版（自己接管鼠标，不走 QDrag）
    # ------------------------------------------------------------------
    # 两种手势必须彻底分开，否则会同时跑：
    #   按在缩略图上拖 -> 调整页序
    #   按在空白处拖   -> 框选多页
    # 以前 mouseMoveEvent 在"还没越过拖拽阈值"那一段统一把事件转给基类，
    # 按住空白处拖动时基类开始框选、我们同时也在算落点并发重排信号，
    # 用户看到的就是"拖动和框选重复了"。
    #
    # 框选也自己实现，不用基类的橡皮筋：实测裸 QListWidget 的框选在 QTest
    # 送事件时选不中任何条目（IconMode / ListMode 都一样），也就是说这条路径
    # 根本没法自动化验证。自己画 + 自己算命中，既能测，也不受平台差异影响。
    _DRAG_NONE = 0    # 还没判定（按下后、未越过阈值）
    _DRAG_PAGE = 1    # 拖整页排序
    _DRAG_BAND = 2    # 框选

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            index = self.indexAt(event.pos())
            self._drag_start = event.pos()
            self._drag_mode = self._DRAG_NONE
            self._dragging = False
            self._drag_row = index.row() if index.isValid() else None
            self._band_rect = None
            # 按在空白处时，基类会执行"点空白=清空选择"；这是期望行为，
            # 所以仍然交给它。按在条目上则照常点选。
            QtWidgets.QListWidget.mousePressEvent(self, event)
            if self._drag_row is None:
                self._band_base = [it for it in self.selectedItems()]
            else:
                self._band_base = []
            return
        QtWidgets.QListWidget.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        if self._drag_start is None or not (event.buttons() & Qt.LeftButton):
            QtWidgets.QListWidget.mouseMoveEvent(self, event)
            return

        if self._drag_mode == self._DRAG_NONE:
            moved = (event.pos() - self._drag_start).manhattanLength()
            if moved < QtWidgets.QApplication.startDragDistance():
                return
            # 越过阈值才判定手势，且只判一次：中途换手势会让用户觉得枪口乱跳
            if self._drag_row is None:
                self._drag_mode = self._DRAG_BAND
            else:
                self._drag_mode = self._DRAG_PAGE
                self._dragging = True

        if self._drag_mode == self._DRAG_BAND:
            self._band_rect = self._band_extent(event.pos())
            self._apply_band_selection()
            self.viewport().update()
            event.accept()
            return

        # 拖页：吃掉事件，基类就不会再去开橡皮筋，两种手势不会叠加
        self._drop_row = self._drop_target(event.pos())
        self.viewport().update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_mode == self._DRAG_PAGE:
            target = self._drop_target(event.pos())
            row = self._drag_row
            self._reset_drag()
            event.accept()
            self._finish_drag(row, target)
            return
        self._reset_drag()
        QtWidgets.QListWidget.mouseReleaseEvent(self, event)

    def _band_extent(self, pos):
        """按下点到当前点构成的矩形（已裁到视口内）。"""
        rect = QtCore.QRect(self._drag_start, pos).normalized()
        return rect.intersected(self.viewport().rect())

    def _apply_band_selection(self):
        """把落在框里的条目设为选中，框外的取消。

        用选中集合整体重算而不是逐个追加：拖动过程中框子可以变大变小，
        只追加的话缩回去时旧的选中退不掉。
        """
        if self._band_rect is None:
            return
        picked = set()
        for row in range(self.count()):
            item = self.item(row)
            if item is None:
                continue
            if self._band_rect.intersects(self.visualItemRect(item)):
                picked.add(id(item))
        self.clearSelection()
        for row in range(self.count()):
            item = self.item(row)
            if item is not None and id(item) in picked:
                item.setSelected(True)
        # 框选期间不要把"当前页"跟着跳，否则正文会一页页乱翻
        if self._band_base:
            for item in self._band_base:
                try:
                    item.setSelected(True)
                except RuntimeError:
                    pass

    def _reset_drag(self):
        self._drag_start = None
        self._drag_row = None
        self._drag_mode = self._DRAG_NONE
        self._dragging = False
        self._drop_row = None
        self._band_rect = None
        self._band_base = []
        self.viewport().update()

    def _finish_drag(self, row, target):
        """松手：算出新页序发出去。真正改文档由主窗口做（要包撤销）。"""
        if row is None:
            return
        moving, at = drop_placement(self.count(), [row], target)
        if not moving or is_noop_move(moving, at):
            return
        order = reorder_indices(self.count(), moving, at)
        if order == list(range(self.count())):
            return
        self.pagesReordered.emit(order)

    def _drop_target(self, pos):
        """光标落在哪个插入位置（行号，count 表示末尾）。"""
        index = self.indexAt(pos)
        if not index.isValid():
            # 落在空白处：按"离哪个格子近"决定插到末尾还是附近
            return self.count()
        rect = self.visualRect(index)
        row = index.row()
        # 看格子的后半（下方或右方）→ 插到它后面。
        # 只判"插到悬停项前面"的话，第 1 格拖到第 2 格等于原地不动。
        if pos.y() > rect.center().y() or pos.x() > rect.center().x():
            return row + 1
        return row

    def paintEvent(self, event):
        QtWidgets.QListWidget.paintEvent(self, event)
        if self._drop_row is not None:
            self._paint_drop_marker()
        if self._band_rect is not None:
            self._paint_band()

    def _paint_band(self):
        """画框选矩形。

        自己实现框选就得自己画，否则拖动时看不到框在哪，
        跟"框选没生效"没法区分。
        """
        rect = self._band_rect
        if rect is None or rect.isEmpty():
            return
        painter = QtGui.QPainter(self.viewport())
        color = QtGui.QColor(COLORS["primary"])
        fill = QtGui.QColor(color)
        fill.setAlpha(38)
        painter.fillRect(rect, fill)
        painter.setPen(QtGui.QPen(color, 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.end()

    def _paint_drop_marker(self):
        """画拖拽落点竖线。

        IconMode 下 Qt 不画落点指示（那是 ListMode 的行为），
        setDropIndicatorShown(True) 在图标模式里等于没开。拖的时候一点反馈
        都没有，用户会以为"拖不动"，所以自己画一条。
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
        if not rect.isValid() or rect.isEmpty():
            return
        painter = QtGui.QPainter(self.viewport())
        painter.setPen(QtGui.QPen(QtGui.QColor(COLORS["primary"]), 3))
        painter.drawLine(x, rect.top(), x, rect.bottom())
        painter.end()


class OutlineTree(QtWidgets.QTreeWidget):
    pageActivated = Signal(int)

    def __init__(self, parent=None):
        QtWidgets.QTreeWidget.__init__(self, parent)
        self.setHeaderHidden(True)
        self.setIndentation(14)
        self.setAnimated(True)
        self.itemClicked.connect(self._on_clicked)

    def set_outline(self, toc):
        self.clear()
        stack = []
        for level, title, page in toc:
            item = QtWidgets.QTreeWidgetItem([title])
            item.setData(0, Qt.UserRole, page - 1)
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                stack[-1][1].addChild(item)
            else:
                self.addTopLevelItem(item)
            stack.append((level, item))
        self.expandAll()

    def _on_clicked(self, item, column):
        page = item.data(0, Qt.UserRole)
        if page is not None and page >= 0:
            self.pageActivated.emit(page)


class AnnotationList(QtWidgets.QListWidget):
    annotationActivated = Signal(int, int)

    def __init__(self, parent=None):
        QtWidgets.QListWidget.__init__(self, parent)
        self.setSpacing(2)
        self.itemClicked.connect(self._on_clicked)

    def set_annotations(self, items):
        self.clear()
        for item in items:
            content = item["content"] or item["type_cn"]
            if len(content) > 40:
                content = content[:40] + "…"
            row = QtWidgets.QListWidgetItem("%d. %s" % (item["page"] + 1, content))
            row.setToolTip(item["content"] or item["type_cn"])
            row.setData(Qt.UserRole, (item["page"], item["xref"]))
            self.addItem(row)
        if not items:
            placeholder = QtWidgets.QListWidgetItem("暂无注释")
            placeholder.setFlags(Qt.NoItemFlags)
            placeholder.setForeground(QtGui.QColor(COLORS["text_sub"]))
            self.addItem(placeholder)

    def _on_clicked(self, item):
        data = item.data(Qt.UserRole)
        if data:
            self.annotationActivated.emit(data[0], data[1])


class SidePanel(QtWidgets.QTabWidget):
    pageActivated = Signal(int)
    annotationActivated = Signal(int, int)
    contextRequested = Signal(list, QtCore.QPoint)
    pagesReordered = Signal(list)

    def __init__(self, parent=None):
        QtWidgets.QTabWidget.__init__(self, parent)
        self.setDocumentMode(True)
        self.thumbs = ThumbnailList()
        self.outline = OutlineTree()
        self.annots = AnnotationList()

        self.addTab(self.thumbs, icons.icon("thumbnails", 16), "")
        self.addTab(self.outline, icons.icon("outline", 16), "")
        self.addTab(self.annots, icons.icon("comment", 16), "")
        self.setTabToolTip(0, "页面缩略图（按住拖动可直接调整页序）")
        self.setTabToolTip(1, "文档目录")
        self.setTabToolTip(2, "注释列表")

        self.thumbs.pageActivated.connect(self.pageActivated)
        self.thumbs.contextRequested.connect(self.contextRequested)
        self.thumbs.pagesReordered.connect(self.pagesReordered)
        self.outline.pageActivated.connect(self.pageActivated)
        self.annots.annotationActivated.connect(self.annotationActivated)

    def set_document(self, doc):
        self.thumbs.set_document(doc)
        if doc is not None and doc.is_open:
            self.outline.set_outline(doc.outline())
        else:
            self.outline.clear()
            self.annots.set_annotations([])

    def refresh(self):
        self.thumbs.refresh_all()
        if self.thumbs.doc is not None and self.thumbs.doc.is_open:
            self.outline.set_outline(self.thumbs.doc.outline())
