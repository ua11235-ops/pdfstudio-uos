# -*- coding: utf-8 -*-
"""页面画布：负责渲染、缩放、以及所有"在页面上动手"的交互。

坐标约定
--------
PyMuPDF 的页面坐标系原点是**左上角**，y 轴向下，单位是点（1/72 英寸）。
画布上的一切换算都以 `self.zoom` 为桥梁：
    控件坐标 = 页面坐标 * zoom + 页边距
"""

import math

from ..qtcompat import QtCore, QtGui, QtWidgets, Qt, Signal, RGB888

from ..core import annotate as annot_mod
from ..core import pageops
from ..core import security
from ..core import textops
from ..core.document import PdfError
from . import icons
from .dialogs import TextInputDialog
from .theme import COLORS

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz


TOOLS = [
    ("select", "选择", "cursor", "选中注释后可拖动、按 Delete 删除"),
    ("hand", "抓手", "hand", "拖动画布浏览页面"),
    ("text_select", "选择文字", "text_select", "框选文字后按 Ctrl+C 复制"),
    ("edit_text", "改字", "edit_text", "点击正文中的文字，直接改写内容"),
    ("highlight", "高亮", "highlight", "框选文字添加高亮"),
    ("underline", "下划线", "underline", "框选文字添加下划线"),
    ("strikeout", "删除线", "strikeout", "框选文字添加删除线"),
    ("ink", "画笔", "ink", "按住鼠标自由手绘"),
    ("rect", "矩形", "rect", "拖出矩形标注框"),
    ("ellipse", "椭圆", "ellipse", "拖出椭圆标注"),
    ("arrow", "箭头", "arrow", "从起点拖到终点画箭头"),
    ("freetext", "文本框", "freetext", "点击页面插入一个带底色的文字框"),
    ("note", "便签", "note", "点击页面添加批注便签"),
    ("redact", "涂黑", "redact", "框选区域永久涂黑（不可恢复内容）"),
    ("eraser", "擦除", "eraser", "点击注释将其删除"),
]

TOOL_NAMES = dict((t[0], t[1]) for t in TOOLS)
TOOL_HINTS = dict((t[0], t[3]) for t in TOOLS)

MIN_ZOOM = 0.1
MAX_ZOOM = 8.0


class PageView(QtWidgets.QWidget):
    pageChanged = Signal(int)
    zoomChanged = Signal(float)
    modified = Signal(str)
    selectionChanged = Signal(object)
    hintChanged = Signal(str)

    MARGIN = 22

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.doc = None
        self.page_index = 0
        self.zoom = 1.0
        self.tool = "select"
        self.color = (1.0, 0.86, 0.24)
        self.line_width = 2.0
        self.opacity = 1.0
        self.font_size = 14

        self._pixmap = None
        self._samples = None
        self._page_w = 595.0
        self._page_h = 842.0
        self._scroll_area = None

        self._drag = None
        self._press_point = None
        self._ink_strokes = []
        self._current_stroke = []
        self._text_sel = None
        self._selected_xref = None
        self._selected_page = None
        self._search_hits = []
        self._drag_annot_rect = None

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.ArrowCursor)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

    # ------------------------------------------------------------------
    # 外部接口
    # ------------------------------------------------------------------
    def attach_scroll_area(self, area):
        self._scroll_area = area

    def set_document(self, doc):
        self.doc = doc
        self.page_index = 0
        self._selected_xref = None
        self._search_hits = []
        self._text_sel = None
        self._pixmap = None
        self._update_size()
        self.update()

    def set_page(self, index, keep_scroll=False):
        if self.doc is None or not self.doc.is_open:
            return
        index = max(0, min(index, self.doc.page_count - 1))
        if index == self.page_index and self._pixmap is not None:
            return
        self.page_index = index
        self.doc.page_index = index
        self._pixmap = None
        self._text_sel = None
        self._selected_xref = None
        self._search_hits = []
        self._update_size()
        self.update()
        self.pageChanged.emit(index)
        if not keep_scroll and self._scroll_area is not None:
            self._scroll_area.verticalScrollBar().setValue(0)

    def set_zoom(self, zoom, anchor=None):
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        if abs(zoom - self.zoom) < 0.0005:
            return
        if anchor is not None and self._scroll_area is not None:
            page_pt = self.to_page(anchor)
            self.zoom = zoom
            self._pixmap = None
            self._update_size()
            widget_pt = self.to_widget(page_pt)
            hbar = self._scroll_area.horizontalScrollBar()
            vbar = self._scroll_area.verticalScrollBar()
            hbar.setValue(int(widget_pt.x() - anchor.x()))
            vbar.setValue(int(widget_pt.y() - anchor.y()))
        else:
            self.zoom = zoom
            self._pixmap = None
            self._update_size()
        self.update()
        self.zoomChanged.emit(self.zoom)

    def fit_width(self):
        if self.doc is None or not self.doc.is_open or self._scroll_area is None:
            return
        available = self._scroll_area.viewport().width() - self.MARGIN * 2 - 8
        width, _height = self.doc.page_size(self.page_index)
        if width > 0:
            self.set_zoom(available / width)

    def fit_page(self):
        if self.doc is None or not self.doc.is_open or self._scroll_area is None:
            return
        avail_w = self._scroll_area.viewport().width() - self.MARGIN * 2 - 8
        avail_h = self._scroll_area.viewport().height() - self.MARGIN * 2 - 8
        width, height = self.doc.page_size(self.page_index)
        if width > 0 and height > 0:
            self.set_zoom(min(avail_w / width, avail_h / height))

    def set_tool(self, name):
        self.tool = name
        cursors = {
            "hand": Qt.OpenHandCursor,
            "text_select": Qt.IBeamCursor,
            "select": Qt.ArrowCursor,
            "eraser": Qt.PointingHandCursor,
        }
        self.setCursor(cursors.get(name, Qt.CrossCursor))
        self.hintChanged.emit(TOOL_HINTS.get(name, ""))
        self.update()

    def set_style(self, color=None, line_width=None, opacity=None, font_size=None):
        if color is not None:
            self.color = color
        if line_width is not None:
            self.line_width = line_width
        if opacity is not None:
            self.opacity = opacity
        if font_size is not None:
            self.font_size = font_size

    def refresh(self):
        self._pixmap = None
        if self.doc is not None and self.doc.is_open:
            if self.page_index >= self.doc.page_count:
                self.page_index = max(0, self.doc.page_count - 1)
            self._update_size()
        self.update()

    def set_search_hits(self, rects, page_index=None):
        if page_index is not None and page_index != self.page_index:
            self._search_hits = []
        else:
            self._search_hits = [self.rectf(r) for r in rects]
        self.update()

    def goto_hit(self, page_index, rect):
        if page_index != self.page_index:
            self.set_page(page_index)
        self._search_hits = [self.rectf(rect)]
        self.update()
        if self._scroll_area is not None:
            center = self.to_widget(QtCore.QPointF(rect[0], rect[1]))
            vbar = self._scroll_area.verticalScrollBar()
            hbar = self._scroll_area.horizontalScrollBar()
            vbar.setValue(int(center.y() - self._scroll_area.viewport().height() / 2))
            hbar.setValue(int(center.x() - self._scroll_area.viewport().width() / 2))

    def reload(self):
        """文档结构变化（撤销、改页数等）后重新同步页码与渲染。"""
        if self.doc is None or not self.doc.is_open:
            return
        self.page_index = max(0, min(self.doc.page_index, self.doc.page_count - 1))
        self._pixmap = None
        self._selected_xref = None
        self._text_sel = None
        self._search_hits = []
        self._update_size()
        self.update()

    def selected_xref(self):
        return self._selected_xref

    def selected_annotation_content(self):
        item = self.selected_annotation()
        return item["content"] if item else ""

    def selected_annotation(self):
        if self._selected_xref is None:
            return None
        for item in annot_mod.list_annotations(self.doc, self._selected_page):
            if item["xref"] == self._selected_xref:
                return item
        return None

    def selection_text(self):
        if self._text_sel is None or self.doc is None:
            return ""
        return self.doc.text_in_rect(self.page_index, self._text_sel)

    def clear_text_selection(self):
        self._text_sel = None
        self.update()

    # ------------------------------------------------------------------
    # 坐标换算
    # ------------------------------------------------------------------
    def to_page(self, point):
        return QtCore.QPointF(
            (point.x() - self.MARGIN) / self.zoom,
            (point.y() - self.MARGIN) / self.zoom,
        )

    def to_widget(self, point):
        return QtCore.QPointF(
            point.x() * self.zoom + self.MARGIN,
            point.y() * self.zoom + self.MARGIN,
        )

    @staticmethod
    def rectf(rect):
        """把 (x0, y0, x1, y1) 元组转成 QRectF（QRectF 的四参构造是 x,y,w,h）。"""
        if isinstance(rect, QtCore.QRectF):
            return rect
        return QtCore.QRectF(
            QtCore.QPointF(rect[0], rect[1]),
            QtCore.QPointF(rect[2], rect[3]),
        ).normalized()

    def to_widget_rect(self, rect):
        tl = self.to_widget(QtCore.QPointF(rect.x(), rect.y()))
        return QtCore.QRectF(tl, QtCore.QSizeF(rect.width() * self.zoom, rect.height() * self.zoom))

    def _update_size(self):
        if self.doc is None or not self.doc.is_open:
            self.setFixedSize(400, 300)
            return
        self._page_w, self._page_h = self.doc.page_size(self.page_index)
        width = int(round(self._page_w * self.zoom)) + self.MARGIN * 2
        height = int(round(self._page_h * self.zoom)) + self.MARGIN * 2
        self.setFixedSize(max(120, width), max(120, height))

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def _ensure_pixmap(self):
        if self.doc is None or not self.doc.is_open:
            self._pixmap = None
            return
        dpr = self.devicePixelRatioF() or 1.0
        samples, width, height, stride, _used = self.doc.render(self.page_index, self.zoom, dpr)
        image = QtGui.QImage(samples, width, height, stride, RGB888)
        pix = QtGui.QPixmap.fromImage(image)
        pix.setDevicePixelRatio(dpr)
        self._samples = samples
        self._pixmap = pix

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QtGui.QColor(COLORS["canvas"]))

        if self.doc is None or not self.doc.is_open:
            painter.setPen(QtGui.QColor(COLORS["text_sub"]))
            font = painter.font()
            font.setPointSize(12)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, "打开一个 PDF 开始工作")
            painter.end()
            return

        if self._pixmap is None:
            self._ensure_pixmap()

        page_rect = QtCore.QRectF(
            self.MARGIN, self.MARGIN,
            self._page_w * self.zoom, self._page_h * self.zoom,
        )

        # 纸张阴影
        for i in range(6, 0, -1):
            alpha = int(10 + i * 2)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QtGui.QColor(60, 70, 90, alpha))
            painter.drawRoundedRect(page_rect.adjusted(-i * 0.4, i * 0.6, i * 0.4, i * 0.8), 3, 3)

        painter.setBrush(QtGui.QColor("#ffffff"))
        painter.setPen(Qt.NoPen)
        painter.drawRect(page_rect)

        if self._pixmap is not None:
            painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(page_rect.topLeft(), self._pixmap)

        self._paint_search_hits(painter)
        self._paint_text_selection(painter)
        self._paint_drag_preview(painter)
        self._paint_selected_annotation(painter)
        painter.end()

    def _paint_search_hits(self, painter):
        if not self._search_hits:
            return
        painter.setPen(QtGui.QPen(QtGui.QColor("#ff9f1a"), 1.2))
        painter.setBrush(QtGui.QColor(255, 200, 60, 90))
        for rect in self._search_hits:
            painter.drawRect(self.to_widget_rect(rect))

    def _paint_text_selection(self, painter):
        if self._text_sel is None:
            return
        painter.setPen(Qt.NoPen)
        painter.setBrush(QtGui.QColor(31, 107, 255, 70))
        painter.drawRect(self.to_widget_rect(self._text_sel))

    def _paint_drag_preview(self, painter):
        if not self._drag:
            return
        kind = self._drag.get("kind")
        if kind in ("rect", "ellipse", "arrow", "redact", "markup", "text_select"):
            rect = self._drag_rect()
            if rect is None:
                return
            widget_rect = self.to_widget_rect(rect)
            if kind == "markup":
                painter.setPen(Qt.NoPen)
                painter.setBrush(QtGui.QColor(
                    int(self.color[0] * 255), int(self.color[1] * 255),
                    int(self.color[2] * 255), 110))
                painter.drawRect(widget_rect)
            elif kind == "redact":
                painter.setPen(QtGui.QPen(QtGui.QColor("#e5484d"), 1.4, Qt.DashLine))
                painter.setBrush(QtGui.QColor(0, 0, 0, 150))
                painter.drawRect(widget_rect)
            elif kind == "text_select":
                painter.setPen(Qt.NoPen)
                painter.setBrush(QtGui.QColor(31, 107, 255, 60))
                painter.drawRect(widget_rect)
            elif kind == "ellipse":
                painter.setPen(QtGui.QPen(QtGui.QColor(self._rgb()), 1.4, Qt.DashLine))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(widget_rect)
            elif kind == "arrow":
                painter.setPen(QtGui.QPen(QtGui.QColor(self._rgb()), 1.6))
                start = self.to_widget(QtCore.QPointF(*self._drag["start"]))
                end = self.to_widget(QtCore.QPointF(*self._drag["end"]))
                painter.drawLine(start, end)
                self._draw_arrow_head(painter, start, end)
            else:
                painter.setPen(QtGui.QPen(QtGui.QColor(self._rgb()), 1.4, Qt.DashLine))
                painter.setBrush(QtGui.QColor(self._rgb(40)))
                painter.drawRect(widget_rect)

        elif kind == "ink":
            painter.setPen(QtGui.QPen(QtGui.QColor(self._rgb()), self.line_width * self.zoom,
                                      Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            for stroke in self._ink_strokes + [self._current_stroke]:
                if len(stroke) < 2:
                    continue
                path = QtGui.QPainterPath(self.to_widget(QtCore.QPointF(*stroke[0])))
                for point in stroke[1:]:
                    path.lineTo(self.to_widget(QtCore.QPointF(*point)))
                painter.drawPath(path)

        elif kind == "move_annot":
            rect = self._drag.get("preview")
            if rect is not None:
                painter.setPen(QtGui.QPen(QtGui.QColor(COLORS["primary"]), 1.4, Qt.DashLine))
                painter.setBrush(QtGui.QColor(31, 107, 255, 40))
                painter.drawRect(self.to_widget_rect(rect))

    def _draw_arrow_head(self, painter, start, end):
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy)
        if length < 1:
            return
        ux, uy = dx / length, dy / length
        size = max(8.0, self.line_width * 4)
        left = QtCore.QPointF(end.x() - ux * size - uy * size * 0.45,
                              end.y() - uy * size + ux * size * 0.45)
        right = QtCore.QPointF(end.x() - ux * size + uy * size * 0.45,
                               end.y() - uy * size - ux * size * 0.45)
        painter.setBrush(QtGui.QColor(self._rgb()))
        painter.drawPolygon([end, left, right])

    def _paint_selected_annotation(self, painter):
        if self._selected_xref is None:
            return
        item = self.selected_annotation()
        if item is None:
            return
        rect = self.to_widget_rect(self.rectf(item["rect"]))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QtGui.QPen(QtGui.QColor(COLORS["primary"]), 1.4, Qt.DashLine))
        painter.drawRect(rect)
        for corner in (rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight()):
            painter.setBrush(QtGui.QColor("#ffffff"))
            painter.setPen(QtGui.QPen(QtGui.QColor(COLORS["primary"]), 1.2))
            painter.drawRect(QtCore.QRectF(corner.x() - 3, corner.y() - 3, 6, 6))

    def _rgb(self, alpha=None):
        r, g, b = [max(0, min(255, int(c * 255))) for c in self.color]
        if alpha is None:
            return QtGui.QColor(r, g, b)
        return QtGui.QColor(r, g, b, alpha)

    # ------------------------------------------------------------------
    # 鼠标交互
    # ------------------------------------------------------------------
    def _drag_rect(self):
        if not self._drag or self._press_point is None:
            return None
        current = self.to_page(self._drag["current"])
        start = self.to_page(self._press_point)
        rect = QtCore.QRectF(start, current).normalized()
        if rect.width() < 1.5 or rect.height() < 1.5:
            return None
        return rect

    def mousePressEvent(self, event):
        if self.doc is None or not self.doc.is_open:
            return
        if event.button() != Qt.LeftButton:
            return
        self.setFocus()
        pos = QtCore.QPointF(event.position() if hasattr(event, "position") else event.pos())
        self._press_point = pos
        page_pt = self.to_page(pos)

        if self.tool == "hand":
            self._drag = {"kind": "pan", "origin": pos,
                          "h": self._scroll_area.horizontalScrollBar().value() if self._scroll_area else 0,
                          "v": self._scroll_area.verticalScrollBar().value() if self._scroll_area else 0}
            self.setCursor(Qt.ClosedHandCursor)
            return

        if self.tool == "select":
            annot = annot_mod.annotation_at(self.doc, self.page_index, (page_pt.x(), page_pt.y()))
            if annot is not None:
                self._selected_xref = annot.xref
                self._selected_page = self.page_index
                self._drag = {"kind": "maybe_move", "start": (page_pt.x(), page_pt.y()),
                              "rect": tuple(annot.rect), "preview": None, "moved": False}
                self.selectionChanged.emit(self.selected_annotation())
                self.update()
            else:
                self._selected_xref = None
                self.selectionChanged.emit(None)
                self.update()
            return

        if self.tool == "eraser":
            annot = annot_mod.annotation_at(self.doc, self.page_index, (page_pt.x(), page_pt.y()))
            if annot is not None:
                self._delete_annotation(annot.xref)
            return

        if self.tool == "edit_text":
            self._begin_edit_text(page_pt)
            return

        if self.tool in ("freetext", "note"):
            self._begin_click_object(page_pt)
            return

        if self.tool == "ink":
            self._drag = {"kind": "ink"}
            self._ink_strokes = []
            self._current_stroke = [(page_pt.x(), page_pt.y())]
            return

        if self.tool == "text_select":
            self._drag = {"kind": "text_select", "current": pos}
            return

        if self.tool in ("highlight", "underline", "strikeout"):
            self._drag = {"kind": "markup", "current": pos}
            return

        if self.tool in ("rect", "ellipse", "redact"):
            self._drag = {"kind": self.tool, "current": pos}
            return

        if self.tool == "arrow":
            self._drag = {"kind": "arrow", "current": pos,
                          "start": (page_pt.x(), page_pt.y()), "end": (page_pt.x(), page_pt.y())}
            return

    def mouseMoveEvent(self, event):
        pos = QtCore.QPointF(event.position() if hasattr(event, "position") else event.pos())
        page_pt = self.to_page(pos)

        if self._drag:
            kind = self._drag.get("kind")
            if kind == "pan" and self._scroll_area is not None:
                delta = pos - self._drag["origin"]
                self._scroll_area.horizontalScrollBar().setValue(int(self._drag["h"] - delta.x()))
                self._scroll_area.verticalScrollBar().setValue(int(self._drag["v"] - delta.y()))
                return
            if kind == "ink":
                self._current_stroke.append((page_pt.x(), page_pt.y()))
                self.update()
                return
            if kind == "arrow":
                self._drag["end"] = (page_pt.x(), page_pt.y())
                self.update()
                return
            if kind == "maybe_move":
                dx = page_pt.x() - self._drag["start"][0]
                dy = page_pt.y() - self._drag["start"][1]
                if not self._drag["moved"] and math.hypot(dx, dy) * self.zoom < 3:
                    return
                self._drag["moved"] = True
                self._drag["kind"] = "move_annot"
                rect = self.rectf(self._drag["rect"])
                rect.translate(dx, dy)
                self._drag["preview"] = rect
                self.update()
                return
            self._drag["current"] = pos
            self.update()
            return

        # 悬停提示
        if self.doc is not None and self.doc.is_open:
            if self.tool == "select":
                annot = annot_mod.annotation_at(self.doc, self.page_index, (page_pt.x(), page_pt.y()))
                self.setCursor(Qt.SizeAllCursor if annot is not None else Qt.ArrowCursor)
            elif self.tool == "eraser":
                annot = annot_mod.annotation_at(self.doc, self.page_index, (page_pt.x(), page_pt.y()))
                self.setCursor(Qt.ForbiddenCursor if annot is None else Qt.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if self._drag is None:
            return
        kind = self._drag.get("kind")
        pos = QtCore.QPointF(event.position() if hasattr(event, "position") else event.pos())

        if kind == "pan":
            self.setCursor(Qt.OpenHandCursor)
            self._drag = None
            return

        if kind == "move_annot":
            rect = self._drag.get("preview")
            self._drag = None
            if rect is not None and self._selected_xref is not None:
                self._apply_move(rect)
            return

        if kind == "maybe_move":
            self._drag = None
            return

        if kind == "ink":
            self._ink_strokes.append(self._current_stroke)
            self._current_stroke = []
            strokes = [s for s in self._ink_strokes if len(s) > 1]
            self._drag = None
            self._ink_strokes = []
            if strokes:
                self._add(lambda page: annot_mod.add_ink(
                    page, strokes, self.color, self.line_width, self.opacity), "手绘标注")
            self.update()
            return

        if kind == "text_select":
            rect = self._drag_rect()
            self._drag = None
            self._text_sel = rect
            self.update()
            if rect is not None:
                text = self.doc.text_in_rect(self.page_index, rect)
                if text.strip():
                    self.hintChanged.emit("已选中 %d 个字符，Ctrl+C 复制" % len(text))
            return

        if kind == "markup":
            rect = self._drag_rect()
            tool = self.tool
            self._drag = None
            self.update()
            if rect is not None:
                self._add(lambda page: annot_mod.add_markup(
                    page, tool, fitz.Rect(rect.x(), rect.y(), rect.x() + rect.width(),
                                          rect.y() + rect.height()),
                    self.color, self.opacity), "文字标注")
            return

        if kind in ("rect", "ellipse"):
            rect = self._drag_rect()
            tool = kind
            self._drag = None
            self.update()
            if rect is not None:
                self._add(lambda page: annot_mod.add_shape(
                    page, tool, fitz.Rect(rect.x(), rect.y(), rect.x() + rect.width(),
                                          rect.y() + rect.height()),
                    self.color, self.line_width, None, self.opacity), "图形标注")
            return

        if kind == "redact":
            rect = self._drag_rect()
            self._drag = None
            self.update()
            if rect is not None:
                self._apply_redact(rect)
            return

        if kind == "arrow":
            start = self._drag.get("start")
            end = self._drag.get("end")
            self._drag = None
            self.update()
            if start and end and math.hypot(end[0] - start[0], end[1] - start[1]) > 3:
                self._add(lambda page: annot_mod.add_arrow(
                    page, start, end, self.color, self.line_width, self.opacity), "箭头标注")
            return

        self._drag = None

    def wheelEvent(self, event):
        if self.doc is None or not self.doc.is_open:
            return
        modifiers = event.modifiers()
        if modifiers & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                pos = QtCore.QPointF(event.position() if hasattr(event, "position") else event.pos())
                factor = 1.15 if delta > 0 else 1 / 1.15
                self.set_zoom(self.zoom * factor, anchor=pos)
            event.accept()
            return
        if self._scroll_area is not None:
            vbar = self._scroll_area.verticalScrollBar()
            delta = event.angleDelta().y()
            at_top = vbar.value() <= 0
            at_bottom = vbar.value() >= vbar.maximum()
            if delta < 0 and at_bottom and self.page_index < self.doc.page_count - 1:
                self.set_page(self.page_index + 1)
                event.accept()
                return
            if delta > 0 and at_top and self.page_index > 0:
                self.set_page(self.page_index - 1)
                if self._scroll_area is not None:
                    self._scroll_area.verticalScrollBar().setValue(
                        self._scroll_area.verticalScrollBar().maximum())
                event.accept()
                return
        event.ignore()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self._selected_xref is not None:
            self._delete_annotation(self._selected_xref)
            return
        if event.key() == Qt.Key_Escape:
            self._drag = None
            self._selected_xref = None
            self._text_sel = None
            self.selectionChanged.emit(None)
            self.update()
            return
        if event.key() in (Qt.Key_PageDown, Qt.Key_PageUp) and self.doc is not None:
            step = 1 if event.key() == Qt.Key_PageDown else -1
            self.set_page(self.page_index + step)
            return
        QtWidgets.QWidget.keyPressEvent(self, event)

    # ------------------------------------------------------------------
    # 具体动作
    # ------------------------------------------------------------------
    def _add(self, action, label):
        """统一的"改动 + 撤销点 + 通知"流程。"""
        self.doc.begin_change(label)
        try:
            result = action(self.doc.doc[self.page_index])
        except Exception as exc:
            self.doc.undo()
            raise PdfError("操作失败：%s" % exc, "action")
        self.doc.end_change()
        self.refresh()
        self.modified.emit(label)
        xref = getattr(result, "xref", None)
        if xref:
            self._selected_xref = xref
            self._selected_page = self.page_index
            self.selectionChanged.emit(self.selected_annotation())
        return result

    def _delete_annotation(self, xref):
        self.doc.begin_change("删除注释")
        annot_mod.delete_annotation(self.doc, self.page_index, xref)
        self.doc.end_change()
        self._selected_xref = None
        self.selectionChanged.emit(None)
        self.refresh()
        self.modified.emit("删除注释")

    def _apply_move(self, rect):
        item = self.selected_annotation()
        if item is None:
            return
        self.doc.begin_change("移动注释")
        try:
            annot_mod.update_annotation(
                self.doc, self._selected_page, item["xref"],
                rect=(rect.x(), rect.y(), rect.x() + rect.width(), rect.y() + rect.height()),
            )
        finally:
            self.doc.end_change()
        self.refresh()
        self.modified.emit("移动注释")

    def _apply_redact(self, rect):
        self.doc.begin_change("涂黑")
        try:
            security.redact_areas(
                self.doc, [(self.page_index, (rect.x(), rect.y(),
                                             rect.x() + rect.width(), rect.y() + rect.height()))]
            )
        except Exception as exc:
            self.doc.undo()
            raise PdfError("涂黑失败：%s" % exc, "redact")
        self.doc.end_change()
        self.refresh()
        self.modified.emit("涂黑")

    def _begin_edit_text(self, page_pt):
        span = self.doc.span_at(self.page_index, (page_pt.x(), page_pt.y()))
        if span is None:
            self.hintChanged.emit("这里没有可编辑的文字（扫描件请先做 OCR）")
            return
        dialog = TextInputDialog(
            "修改文字",
            "直接编辑下面的内容，确定后会替换页面上的原文：",
            span["text"].strip(),
            self,
        )
        if not dialog.exec_dialog():
            return
        new_text = dialog.text_value()
        self.doc.begin_change("修改文字")
        try:
            page = self.doc.doc[self.page_index]
            background = textops.page_background_color(page)
            textops.replace_span_text(page, span, new_text, fill=background)
        except Exception as exc:
            self.doc.undo()
            raise PdfError("修改文字失败：%s" % exc, "text")
        self.doc.end_change()
        self.refresh()
        self.modified.emit("修改文字")
        self.hintChanged.emit("已替换文字")

    def _begin_click_object(self, page_pt):
        tool = self.tool
        if tool == "freetext":
            dialog = TextInputDialog("插入文字", "输入要放到页面上的文字：", "", self)
            if not dialog.exec_dialog():
                return
            text = dialog.text_value()
            if not text.strip():
                return
            width = max(120.0, min(self._page_w - page_pt.x() - 20, 420))
            rect = fitz.Rect(page_pt.x(), page_pt.y(), page_pt.x() + width,
                             page_pt.y() + max(36.0, self.font_size * 2.2))
            self._add(lambda page: annot_mod.add_textbox(
                page, rect, text, self.font_size, (0.12, 0.12, 0.12),
                (1.0, 0.97, 0.86), (0.94, 0.74, 0.20), 0, self.opacity),
                "文本框")
        else:
            dialog = TextInputDialog("添加便签", "便签内容：", "", self)
            if not dialog.exec_dialog():
                return
            text = dialog.text_value()
            if not text.strip():
                return
            self._add(lambda page: annot_mod.add_note(
                page, (page_pt.x(), page_pt.y()), text, self.color), "便签")

    # ------------------------------------------------------------------
    # 页面操作（供菜单调用）
    # ------------------------------------------------------------------
    def rotate_current(self, angle):
        self.doc.begin_change("旋转页面")
        pageops.rotate_pages(self.doc, [self.page_index], angle)
        self.doc.end_change()
        self.refresh()
        self.modified.emit("旋转页面")

    def insert_blank(self):
        self.doc.begin_change("插入空白页")
        pageops.insert_blank_page(self.doc, self.page_index + 1, self._page_w, self._page_h)
        self.doc.end_change()
        self.set_page(self.page_index + 1)
        self.modified.emit("插入空白页")

    def delete_current(self):
        if self.doc.page_count <= 1:
            raise PdfError("不能删除最后一页", "last_page")
        index = self.page_index
        self.doc.begin_change("删除页面")
        pageops.delete_pages(self.doc, [index])
        self.doc.end_change()
        self.set_page(min(index, self.doc.page_count - 1))
        self.modified.emit("删除页面")
