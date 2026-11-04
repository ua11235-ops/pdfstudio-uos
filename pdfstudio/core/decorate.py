# -*- coding: utf-8 -*-
"""页面装饰：水印、页码、页眉页脚。

水印直接写入页面内容流（而不是做成注释），这样任何阅读器都能看到，
导出、打印也不会丢。
"""

import math

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from .document import PdfError
from .annotate import CJK_FONT


def _blend_to_white(color, opacity):
    """把透明度换算成"与白底混合后的颜色"，等效于视觉上的半透明。"""
    opacity = max(0.0, min(1.0, opacity))
    return tuple(round(c * opacity + (1.0 - opacity), 4) for c in color)


def _text_width(text, font_size, fontname=CJK_FONT):
    try:
        return fitz.get_text_length(text, fontname=fontname, fontsize=font_size)
    except Exception:
        return len(text) * font_size * 0.6


def add_watermark(doc, text, font_size=50, color=(0.55, 0.55, 0.55), opacity=0.15,
                  angle=45, mode="sparse", x_gap=220, y_gap=160, pages=None):
    """给指定页面加水印。mode: sparse（居中一个）/ dense（平铺）。"""
    if not text:
        raise PdfError("水印文字不能为空", "watermark")
    targets = pages if pages is not None else range(doc.page_count)
    ink = _blend_to_white(color, opacity)
    mat = fitz.Matrix(1, 1).prerotate(-angle)

    count = 0
    for page_index in targets:
        page = doc.doc[page_index]
        rect = page.rect
        if mode == "dense":
            step_x = max(60.0, x_gap)
            step_y = max(50.0, y_gap)
            y = rect.y0 + step_y * 0.5
            while y < rect.y1 + step_y:
                x = rect.x0 + step_x * 0.5
                while x < rect.x1 + step_x:
                    _stamp(page, text, fitz.Point(x, y), font_size, ink, mat, center=True)
                    x += step_x
                y += step_y
        else:
            pivot = fitz.Point(rect.width / 2.0, rect.height / 2.0)
            _stamp(page, text, pivot, font_size, ink, mat, center=True)
        count += 1
    return count


def _stamp(page, text, point, font_size, color, mat, center=False):
    width = _text_width(text, font_size)
    x = point.x - width / 2.0 if center else point.x
    y = point.y + font_size * 0.35 if center else point.y
    try:
        page.insert_text(
            fitz.Point(x, y),
            text,
            fontsize=font_size,
            fontname=CJK_FONT,
            color=color,
            morph=(point, mat),
            overlay=True,
        )
    except Exception:
        # 极旧版本不支持 morph 时退化为水平文字
        page.insert_text(
            fitz.Point(x, y), text, fontsize=font_size, fontname=CJK_FONT, color=color
        )


POSITIONS = [
    ("bottom_center", "底部居中"),
    ("bottom_left", "底部靠左"),
    ("bottom_right", "底部靠右"),
    ("top_center", "顶部居中"),
    ("top_left", "顶部靠左"),
    ("top_right", "顶部靠右"),
]


def add_page_numbers(doc, position="bottom_center", template="{page} / {total}",
                     start_number=1, font_size=10, color=(0.2, 0.2, 0.2),
                     margin=36, pages=None, skip_first=False):
    """添加页码。template 支持 {page} 与 {total} 占位符。"""
    targets = list(pages) if pages is not None else list(range(doc.page_count))
    if skip_first and targets:
        targets = targets[1:]
    total = doc.page_count
    for order, page_index in enumerate(targets):
        page = doc.doc[page_index]
        rect = page.rect
        label = (template or "{page}").replace("{page}", str(start_number + order))
        label = label.replace("{total}", str(start_number + len(targets) - 1))
        width = _text_width(label, font_size)
        height = font_size
        if position.startswith("bottom"):
            y = rect.y1 - margin
        else:
            y = rect.y0 + margin + height
        if position.endswith("left"):
            x = rect.x0 + margin
        elif position.endswith("right"):
            x = rect.x1 - margin - width
        else:
            x = (rect.width - width) / 2.0
        page.insert_text(
            fitz.Point(x, y), label, fontsize=font_size, fontname=CJK_FONT, color=color
        )
    return len(targets)


def add_header_footer(doc, header="", footer="", font_size=9,
                      color=(0.35, 0.35, 0.35), margin=28, pages=None):
    targets = pages if pages is not None else range(doc.page_count)
    for page_index in targets:
        page = doc.doc[page_index]
        rect = page.rect
        if header:
            width = _text_width(header, font_size)
            page.insert_text(
                fitz.Point((rect.width - width) / 2.0, rect.y0 + margin),
                header, fontsize=font_size, fontname=CJK_FONT, color=color,
            )
        if footer:
            width = _text_width(footer, font_size)
            page.insert_text(
                fitz.Point((rect.width - width) / 2.0, rect.y1 - margin + font_size),
                footer, fontsize=font_size, fontname=CJK_FONT, color=color,
            )


def add_bates_numbering(doc, prefix="", start=1, digits=6, position="bottom_right",
                        font_size=9, color=(0.2, 0.2, 0.2), margin=28):
    """卷宗编号（法律 / 归档常用）。"""
    for order in range(doc.page_count):
        page = doc.doc[order]
        rect = page.rect
        label = "%s%0*d" % (prefix, digits, start + order)
        width = _text_width(label, font_size)
        if position.endswith("right"):
            x = rect.x1 - margin - width
        elif position.endswith("left"):
            x = rect.x0 + margin
        else:
            x = (rect.width - width) / 2.0
        y = rect.y1 - margin if position.startswith("bottom") else rect.y0 + margin + font_size
        page.insert_text(
            fitz.Point(x, y), label, fontsize=font_size, fontname=CJK_FONT, color=color
        )
