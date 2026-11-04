# -*- coding: utf-8 -*-
"""用 QPainter 现场绘制的矢量图标。

不依赖系统图标主题 / 图标字体，因此在 UOS、Deepin、Ubuntu 上外观完全一致。
所有图形都画在 24x24 的逻辑坐标系里，再按需要的尺寸缩放。
"""

from ..qtcompat import QtCore, QtGui, Qt

from ..qtcompat import QtWidgets  # noqa: F401  (保证 QtWidgets 已加载)

_DEFAULT_COLOR = "#3d4450"


def _pen(color, width=1.7):
    pen = QtGui.QPen(QtGui.QColor(color))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _draw(name, p, color):
    """在 24x24 坐标系内绘制指定图标。"""
    p.setPen(_pen(color))
    p.setBrush(Qt.NoBrush)

    if name == "open":
        p.drawPolyline([QtCore.QPointF(3, 18), QtCore.QPointF(3, 6), QtCore.QPointF(9.5, 6),
                        QtCore.QPointF(11.5, 9), QtCore.QPointF(20, 9)])
        p.drawPolyline([QtCore.QPointF(3, 18), QtCore.QPointF(6.5, 11.5), QtCore.QPointF(22, 11.5),
                        QtCore.QPointF(18.5, 18), QtCore.QPointF(3, 18)])

    elif name in ("save", "saveas"):
        p.drawRoundedRect(QtCore.QRectF(4, 4, 16, 16), 2, 2)
        p.drawRect(QtCore.QRectF(8, 4, 8, 5))
        p.drawRect(QtCore.QRectF(7, 13, 10, 7))
        if name == "saveas":
            p.setBrush(QtGui.QColor(color))
            p.drawEllipse(QtCore.QPointF(18, 18), 3.4, 3.4)

    elif name in ("undo", "redo"):
        p.save()
        if name == "redo":
            p.translate(24, 0)
            p.scale(-1, 1)
        path = QtGui.QPainterPath(QtCore.QPointF(6, 10))
        path.cubicTo(9, 4.5, 17, 4.5, 19, 10)
        path.cubicTo(20.4, 14, 17.5, 17, 13, 17)
        p.drawPath(path)
        p.drawPolyline([QtCore.QPointF(6, 5.5), QtCore.QPointF(6, 10.2), QtCore.QPointF(11, 10.2)])
        p.restore()

    elif name in ("zoom_in", "zoom_out"):
        p.drawEllipse(QtCore.QPointF(10.5, 10.5), 6.5, 6.5)
        p.drawLine(QtCore.QPointF(15.3, 15.3), QtCore.QPointF(20.5, 20.5))
        p.drawLine(QtCore.QPointF(7.5, 10.5), QtCore.QPointF(13.5, 10.5))
        if name == "zoom_in":
            p.drawLine(QtCore.QPointF(10.5, 7.5), QtCore.QPointF(10.5, 13.5))

    elif name == "fit_width":
        p.drawRect(QtCore.QRectF(3, 6, 18, 12))
        p.drawLine(QtCore.QPointF(7, 9), QtCore.QPointF(7, 15))
        p.drawLine(QtCore.QPointF(17, 9), QtCore.QPointF(17, 15))
        p.drawLine(QtCore.QPointF(9, 12), QtCore.QPointF(15, 12))

    elif name == "fit_page":
        p.drawRect(QtCore.QRectF(4.5, 3.5, 15, 17))
        p.drawLine(QtCore.QPointF(8, 8), QtCore.QPointF(16, 8))
        p.drawLine(QtCore.QPointF(8, 12), QtCore.QPointF(16, 12))
        p.drawLine(QtCore.QPointF(8, 16), QtCore.QPointF(13, 16))

    elif name == "prev":
        p.drawPolyline([QtCore.QPointF(15, 5), QtCore.QPointF(8, 12), QtCore.QPointF(15, 19)])
    elif name == "next":
        p.drawPolyline([QtCore.QPointF(9, 5), QtCore.QPointF(16, 12), QtCore.QPointF(9, 19)])
    elif name == "first":
        p.drawLine(QtCore.QPointF(6, 5), QtCore.QPointF(6, 19))
        p.drawPolyline([QtCore.QPointF(18, 5), QtCore.QPointF(10, 12), QtCore.QPointF(18, 19)])
    elif name == "last":
        p.drawLine(QtCore.QPointF(18, 5), QtCore.QPointF(18, 19))
        p.drawPolyline([QtCore.QPointF(6, 5), QtCore.QPointF(14, 12), QtCore.QPointF(6, 19)])

    elif name == "hand":
        path = QtGui.QPainterPath(QtCore.QPointF(8, 20))
        path.lineTo(6, 13)
        path.lineTo(6, 10)
        path.cubicTo(6, 8.6, 8.4, 8.6, 8.4, 10)
        path.lineTo(8.4, 6.2)
        path.cubicTo(8.4, 4.6, 11, 4.6, 11, 6.2)
        path.lineTo(11, 9.6)
        path.lineTo(11, 5.2)
        path.cubicTo(11, 3.6, 13.6, 3.6, 13.6, 5.2)
        path.lineTo(13.6, 9.8)
        path.lineTo(13.6, 6.4)
        path.cubicTo(13.6, 4.9, 16.1, 4.9, 16.1, 6.4)
        path.lineTo(16.1, 12.5)
        path.cubicTo(16.1, 17, 14.6, 20, 11.4, 20)
        p.drawPath(path)

    elif name == "cursor":
        p.setBrush(QtGui.QColor(color))
        p.drawPolygon([QtCore.QPointF(7, 3.5), QtCore.QPointF(7, 18), QtCore.QPointF(10.6, 14.6),
                       QtCore.QPointF(13, 20.5), QtCore.QPointF(15.6, 19.4), QtCore.QPointF(13.2, 13.8),
                       QtCore.QPointF(18, 13.6)])

    elif name == "text_select":
        p.drawLine(QtCore.QPointF(8, 5), QtCore.QPointF(16, 5))
        p.drawLine(QtCore.QPointF(8, 19), QtCore.QPointF(16, 19))
        p.drawLine(QtCore.QPointF(12, 5), QtCore.QPointF(12, 19))
        p.drawLine(QtCore.QPointF(9.5, 8), QtCore.QPointF(14.5, 8))

    elif name == "highlight":
        p.setBrush(QtGui.QColor(color))
        p.setPen(Qt.NoPen)
        p.save()
        p.translate(12, 12)
        p.rotate(-40)
        p.drawRoundedRect(QtCore.QRectF(-7, -4, 14, 6), 1.2, 1.2)
        p.restore()
        p.setPen(_pen(color, 2.4))
        p.drawLine(QtCore.QPointF(4, 20), QtCore.QPointF(20, 20))

    elif name in ("underline", "strikeout"):
        p.drawPolyline([QtCore.QPointF(8, 5), QtCore.QPointF(8, 11),
                        QtCore.QPointF(12, 14.5), QtCore.QPointF(16, 11), QtCore.QPointF(16, 5)])
        if name == "underline":
            p.drawLine(QtCore.QPointF(5.5, 18.5), QtCore.QPointF(18.5, 18.5))
        else:
            p.drawLine(QtCore.QPointF(5, 12.2), QtCore.QPointF(19, 12.2))

    elif name == "ink":
        p.setBrush(QtGui.QColor(color))
        p.drawPolygon([QtCore.QPointF(5, 19), QtCore.QPointF(6.4, 14.6), QtCore.QPointF(16.6, 4.4),
                       QtCore.QPointF(19.6, 7.4), QtCore.QPointF(9.4, 17.6)])
        p.setBrush(Qt.NoBrush)
        p.drawLine(QtCore.QPointF(6.4, 14.6), QtCore.QPointF(9.4, 17.6))

    elif name in ("rect", "ellipse", "redact"):
        if name == "ellipse":
            p.drawEllipse(QtCore.QRectF(4, 6.5, 16, 11))
        else:
            if name == "redact":
                p.setBrush(QtGui.QColor(color))
            p.drawRoundedRect(QtCore.QRectF(4, 6.5, 16, 11), 1.2, 1.2)

    elif name == "arrow":
        p.drawLine(QtCore.QPointF(5, 19), QtCore.QPointF(18, 6))
        p.drawPolyline([QtCore.QPointF(11.5, 6), QtCore.QPointF(18, 6), QtCore.QPointF(18, 12.5)])

    elif name == "freetext":
        p.drawRoundedRect(QtCore.QRectF(3.5, 4.5, 17, 15), 2, 2)
        p.drawLine(QtCore.QPointF(8, 8.5), QtCore.QPointF(16, 8.5))
        p.drawLine(QtCore.QPointF(12, 8.5), QtCore.QPointF(12, 15.5))
        p.drawLine(QtCore.QPointF(9.5, 15.5), QtCore.QPointF(14.5, 15.5))

    elif name == "note":
        p.drawPolygon([QtCore.QPointF(4, 4), QtCore.QPointF(20, 4), QtCore.QPointF(20, 15),
                       QtCore.QPointF(15, 20), QtCore.QPointF(4, 20)])
        p.drawPolyline([QtCore.QPointF(15, 20), QtCore.QPointF(15, 15), QtCore.QPointF(20, 15)])
        p.drawLine(QtCore.QPointF(7.5, 9), QtCore.QPointF(16.5, 9))
        p.drawLine(QtCore.QPointF(7.5, 12.5), QtCore.QPointF(13.5, 12.5))

    elif name == "eraser":
        p.drawPolygon([QtCore.QPointF(4, 16), QtCore.QPointF(12, 5), QtCore.QPointF(20, 11),
                       QtCore.QPointF(13, 19)])
        p.drawLine(QtCore.QPointF(8, 9.5), QtCore.QPointF(15.5, 15.5))
        p.drawLine(QtCore.QPointF(9, 19), QtCore.QPointF(20, 19))

    elif name == "search":
        p.drawEllipse(QtCore.QPointF(10.5, 10.5), 6, 6)
        p.drawLine(QtCore.QPointF(15, 15), QtCore.QPointF(20.5, 20.5))

    elif name == "trash":
        p.drawLine(QtCore.QPointF(4, 7), QtCore.QPointF(20, 7))
        p.drawLine(QtCore.QPointF(9.5, 4.5), QtCore.QPointF(14.5, 4.5))
        p.drawPolyline([QtCore.QPointF(6, 7), QtCore.QPointF(7, 20), QtCore.QPointF(17, 20),
                        QtCore.QPointF(18, 7)])
        p.drawLine(QtCore.QPointF(10, 10.5), QtCore.QPointF(10, 16.5))
        p.drawLine(QtCore.QPointF(14, 10.5), QtCore.QPointF(14, 16.5))

    elif name in ("rotate_l", "rotate_r"):
        p.save()
        if name == "rotate_r":
            p.translate(24, 0)
            p.scale(-1, 1)
        path = QtGui.QPainterPath(QtCore.QPointF(5.5, 12))
        path.arcTo(QtCore.QRectF(5.5, 5.5, 13, 13), 90, -260)
        p.drawPath(path)
        p.drawPolyline([QtCore.QPointF(4, 7), QtCore.QPointF(5.6, 12.2), QtCore.QPointF(10.5, 10.6)])
        p.restore()

    elif name == "print":
        p.drawRoundedRect(QtCore.QRectF(6.5, 3.5, 11, 5), 1, 1)
        p.drawRoundedRect(QtCore.QRectF(3.5, 8.5, 17, 8), 1.5, 1.5)
        p.drawRect(QtCore.QRectF(6.5, 14, 11, 6.5))

    elif name == "export":
        p.drawPolyline([QtCore.QPointF(4, 15), QtCore.QPointF(4, 20), QtCore.QPointF(20, 20),
                        QtCore.QPointF(20, 15)])
        p.drawLine(QtCore.QPointF(12, 4), QtCore.QPointF(12, 16))
        p.drawPolyline([QtCore.QPointF(7.5, 8.5), QtCore.QPointF(12, 4), QtCore.QPointF(16.5, 8.5)])

    elif name in ("lock", "unlock"):
        p.drawRoundedRect(QtCore.QRectF(5, 11, 14, 9.5), 2, 2)
        p.setBrush(Qt.NoBrush)
        if name == "lock":
            p.drawArc(QtCore.QRectF(7.8, 3.5, 8.4, 12), 0, 180 * 16)
        else:
            p.drawArc(QtCore.QRectF(7.8, 3.5, 8.4, 12), 40 * 16, 140 * 16)
        p.drawEllipse(QtCore.QPointF(12, 15.5), 1.3, 1.3)

    elif name == "watermark":
        p.save()
        p.translate(12, 12)
        p.rotate(-35)
        p.setPen(_pen(color, 1.6))
        p.drawLine(QtCore.QPointF(-7.5, 0), QtCore.QPointF(7.5, 0))
        p.drawLine(QtCore.QPointF(-5.5, 4.5), QtCore.QPointF(5.5, 4.5))
        p.drawLine(QtCore.QPointF(-3.5, -4.5), QtCore.QPointF(3.5, -4.5))
        p.restore()
        p.setPen(_pen(color, 1.2))
        p.drawRect(QtCore.QRectF(3, 3, 18, 18))

    elif name == "pages":
        p.drawRect(QtCore.QRectF(3.5, 3.5, 8, 8))
        p.drawRect(QtCore.QRectF(12.5, 3.5, 8, 8))
        p.drawRect(QtCore.QRectF(3.5, 12.5, 8, 8))
        p.drawRect(QtCore.QRectF(12.5, 12.5, 8, 8))

    elif name == "form":
        p.drawRect(QtCore.QRectF(4, 3.5, 16, 17))
        p.drawRect(QtCore.QRectF(7, 7, 10, 3.2))
        p.drawRect(QtCore.QRectF(7, 13, 10, 3.2))

    elif name == "settings":
        p.drawEllipse(QtCore.QPointF(12, 12), 3.2, 3.2)
        p.drawEllipse(QtCore.QPointF(12, 12), 7.5, 7.5)
        for angle in range(0, 360, 45):
            p.save()
            p.translate(12, 12)
            p.rotate(angle)
            p.drawLine(QtCore.QPointF(0, -7.5), QtCore.QPointF(0, -10.5))
            p.restore()

    elif name == "doc":
        p.drawPolygon([QtCore.QPointF(5, 3), QtCore.QPointF(14.5, 3), QtCore.QPointF(19, 7.5),
                       QtCore.QPointF(19, 21), QtCore.QPointF(5, 21)])
        p.drawPolyline([QtCore.QPointF(14.5, 3), QtCore.QPointF(14.5, 7.5), QtCore.QPointF(19, 7.5)])
        p.drawLine(QtCore.QPointF(8, 12), QtCore.QPointF(16, 12))
        p.drawLine(QtCore.QPointF(8, 15.5), QtCore.QPointF(16, 15.5))

    elif name == "thumbnails":
        p.drawRect(QtCore.QRectF(3.5, 3.5, 7, 17))
        p.drawRect(QtCore.QRectF(13, 3.5, 7.5, 5))
        p.drawRect(QtCore.QRectF(13, 10.5, 7.5, 5))
        p.drawRect(QtCore.QRectF(13, 17.5, 7.5, 3))

    elif name == "outline":
        p.drawLine(QtCore.QPointF(8, 6), QtCore.QPointF(20, 6))
        p.drawLine(QtCore.QPointF(8, 12), QtCore.QPointF(20, 12))
        p.drawLine(QtCore.QPointF(8, 18), QtCore.QPointF(20, 18))
        p.setBrush(QtGui.QColor(color))
        for y in (6, 12, 18):
            p.drawEllipse(QtCore.QPointF(4.2, y), 1.3, 1.3)

    elif name == "comment":
        p.drawRoundedRect(QtCore.QRectF(3, 4.5, 18, 12), 3, 3)
        p.drawPolyline([QtCore.QPointF(8, 16.5), QtCore.QPointF(8, 20.5), QtCore.QPointF(12.5, 16.5)])

    elif name == "edit_text":
        p.drawLine(QtCore.QPointF(6, 5), QtCore.QPointF(13, 5))
        p.drawLine(QtCore.QPointF(9.5, 5), QtCore.QPointF(9.5, 17))
        p.drawLine(QtCore.QPointF(7, 17), QtCore.QPointF(12, 17))
        p.setBrush(QtGui.QColor(color))
        p.drawPolygon([QtCore.QPointF(14, 18.5), QtCore.QPointF(14.8, 14.6),
                       QtCore.QPointF(20.5, 8.9), QtCore.QPointF(22.4, 10.8),
                       QtCore.QPointF(16.7, 16.5)])

    elif name == "info":
        p.drawEllipse(QtCore.QPointF(12, 12), 8.5, 8.5)
        p.drawLine(QtCore.QPointF(12, 11), QtCore.QPointF(12, 16.5))
        p.setBrush(QtGui.QColor(color))
        p.drawEllipse(QtCore.QPointF(12, 7.8), 1.05, 1.05)

    elif name == "merge":
        p.drawPolyline([QtCore.QPointF(4, 6), QtCore.QPointF(9, 6), QtCore.QPointF(12, 12),
                        QtCore.QPointF(15, 6), QtCore.QPointF(20, 6)])
        p.drawLine(QtCore.QPointF(12, 12), QtCore.QPointF(12, 20))
        p.drawPolyline([QtCore.QPointF(9, 17), QtCore.QPointF(12, 20), QtCore.QPointF(15, 17)])

    elif name == "split":
        p.drawLine(QtCore.QPointF(12, 3), QtCore.QPointF(12, 10))
        p.drawPolyline([QtCore.QPointF(8, 7), QtCore.QPointF(12, 11), QtCore.QPointF(16, 7)])
        p.drawLine(QtCore.QPointF(4, 14), QtCore.QPointF(9, 14))
        p.drawLine(QtCore.QPointF(15, 14), QtCore.QPointF(20, 14))
        p.drawLine(QtCore.QPointF(4, 20), QtCore.QPointF(9, 20))
        p.drawLine(QtCore.QPointF(15, 20), QtCore.QPointF(20, 20))

    elif name == "plus":
        p.drawLine(QtCore.QPointF(12, 5), QtCore.QPointF(12, 19))
        p.drawLine(QtCore.QPointF(5, 12), QtCore.QPointF(19, 12))

    elif name == "minus":
        p.drawLine(QtCore.QPointF(5, 12), QtCore.QPointF(19, 12))

    elif name == "grid":
        p.drawRect(QtCore.QRectF(3.5, 3.5, 17, 17))
        p.drawLine(QtCore.QPointF(3.5, 9), QtCore.QPointF(20.5, 9))
        p.drawLine(QtCore.QPointF(3.5, 15), QtCore.QPointF(20.5, 15))
        p.drawLine(QtCore.QPointF(9.5, 3.5), QtCore.QPointF(9.5, 20.5))
        p.drawLine(QtCore.QPointF(15.5, 3.5), QtCore.QPointF(15.5, 20.5))

    else:  # 兜底：画个文档
        p.drawRect(QtCore.QRectF(6, 3.5, 12, 17))


def pixmap(name, size=20, color=_DEFAULT_COLOR, ratio=1.0):
    px = int(round(size * ratio))
    pm = QtGui.QPixmap(px, px)
    pm.fill(Qt.transparent)
    painter = QtGui.QPainter(pm)
    painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
    painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
    scale = px / 24.0
    painter.scale(scale, scale)
    try:
        _draw(name, painter, color)
    finally:
        painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name, size=20, color=_DEFAULT_COLOR, disabled_color=None):
    """生成 QIcon。禁用态由 Qt 自动变淡，这里只提供正常态。"""
    ic = QtGui.QIcon()
    ic.addPixmap(pixmap(name, size, color, 1.0), QtGui.QIcon.Normal, QtGui.QIcon.Off)
    ic.addPixmap(pixmap(name, size, color, 2.0), QtGui.QIcon.Normal, QtGui.QIcon.Off)
    ic.addPixmap(pixmap(name, size, color, 1.0), QtGui.QIcon.Active, QtGui.QIcon.Off)
    ic.addPixmap(pixmap(name, size, "#ffffff", 1.0), QtGui.QIcon.Selected, QtGui.QIcon.Off)
    ic.addPixmap(pixmap(name, size, "#ffffff", 2.0), QtGui.QIcon.Selected, QtGui.QIcon.Off)
    return ic


def app_icon(size=256):
    """应用图标：蓝底白色文档 + 高亮笔触。"""
    pm = QtGui.QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QtGui.QPainter(pm)
    painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
    grad = QtGui.QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QtGui.QColor("#2f7bff"))
    grad.setColorAt(1.0, QtGui.QColor("#1650c9"))
    painter.setBrush(QtGui.QBrush(grad))
    painter.setPen(Qt.NoPen)
    radius = size * 0.22
    painter.drawRoundedRect(QtCore.QRectF(0, 0, size, size), radius, radius)

    painter.setBrush(QtGui.QColor("#ffffff"))
    w = size * 0.46
    h = size * 0.58
    x = (size - w) / 2.0
    y = (size - h) / 2.0
    painter.drawRoundedRect(QtCore.QRectF(x, y, w, h), size * 0.04, size * 0.04)

    painter.setPen(QtGui.QPen(QtGui.QColor("#c9d8f5"), size * 0.028))
    for i in range(3):
        ly = y + h * (0.26 + i * 0.17)
        painter.drawLine(QtCore.QPointF(x + w * 0.16, ly), QtCore.QPointF(x + w * 0.84, ly))

    painter.setPen(Qt.NoPen)
    painter.setBrush(QtGui.QColor("#ffd23f"))
    painter.save()
    painter.translate(size * 0.5, size * 0.76)
    painter.rotate(-18)
    painter.drawRoundedRect(QtCore.QRectF(-w * 0.42, -h * 0.07, w * 0.84, h * 0.14),
                            size * 0.02, size * 0.02)
    painter.restore()
    painter.end()
    return pm
