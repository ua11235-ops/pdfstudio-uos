# -*- coding: utf-8 -*-
"""注释（高亮、下划线、删除线、手绘、图形、文本框、便签、图章）。"""

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from .document import PdfError

# 常用颜色（RGB 0~1）
COLOR_PRESETS = [
    ("黄色", (1.0, 0.86, 0.24)),
    ("绿色", (0.35, 0.85, 0.42)),
    ("蓝色", (0.32, 0.62, 1.0)),
    ("红色", (0.98, 0.35, 0.35)),
    ("紫色", (0.68, 0.45, 1.0)),
    ("灰色", (0.62, 0.65, 0.70)),
]

CJK_FONT = "china-s"  # PyMuPDF 内置简体中文字体，无需外部字体文件

_CJK_RANGES = (
    (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
    (0x3000, 0x303F), (0xFF00, 0xFFEF),
)


def _has_cjk(text):
    for ch in text or "":
        code = ord(ch)
        for low, high in _CJK_RANGES:
            if low <= code <= high:
                return True
    return False


def _words_in_rect(page, rect):
    try:
        words = page.get_text("words", clip=rect)
    except Exception:
        words = []
    if not words:
        # 退化：把整个矩形当作一行
        return []
    words = sorted(words, key=lambda w: (round(w[1], 1), w[0]))
    return words


def add_markup(page, kind, rect, color, opacity=1.0, line_width=1.0):
    """在 rect 覆盖的文字上添加文本标记，返回 annot 或 None。"""
    rect = fitz.Rect(rect)
    if rect.is_empty or rect.width < 1 or rect.height < 1:
        return None
    words = _words_in_rect(page, rect)
    # PyMuPDF 的 add_*_annot 既接受 Quad 列表也接受 Rect 列表，
    # 用 Rect 可以避开旧版本 Quad 构造函数的兼容问题。
    quads = [fitz.Rect(w[:4]) for w in words]
    if not quads:
        return None
    if kind == "highlight":
        annot = page.add_highlight_annot(quads)
    elif kind == "underline":
        annot = page.add_underline_annot(quads)
    elif kind == "strikeout":
        annot = page.add_strikeout_annot(quads)
    elif kind == "squiggly":
        annot = page.add_squiggly_annot(quads)
    else:
        raise PdfError("未知的标记类型：%s" % kind, "annot")
    annot.set_colors(stroke=color)
    try:
        annot.set_opacity(opacity)
    except Exception:
        pass
    annot.update()
    return annot


def add_ink(page, strokes, color, width=2.0, opacity=1.0):
    points = [[tuple(p) for p in stroke] for stroke in strokes if len(stroke) > 1]
    if not points:
        return None
    annot = page.add_ink_annot(points)
    annot.set_colors(stroke=color)
    annot.set_border(width=width)
    try:
        annot.set_opacity(opacity)
    except Exception:
        pass
    annot.update()
    return annot


def add_shape(page, kind, rect, color, width=2.0, fill=None, opacity=1.0):
    rect = fitz.Rect(rect)
    rect.normalize()
    if rect.width < 2 or rect.height < 2:
        return None
    if kind == "rect":
        annot = page.add_rect_annot(rect)
    elif kind == "ellipse":
        annot = page.add_circle_annot(rect)
    elif kind == "line":
        annot = page.add_line_annot(rect.tl, rect.br)
    else:
        raise PdfError("未知的图形类型：%s" % kind, "annot")
    annot.set_colors(stroke=color, fill=fill)
    annot.set_border(width=width)
    try:
        annot.set_opacity(opacity)
    except Exception:
        pass
    annot.update()
    return annot


def add_arrow(page, start, end, color, width=2.0, opacity=1.0):
    annot = page.add_line_annot(fitz.Point(start), fitz.Point(end))
    annot.set_colors(stroke=color)
    annot.set_border(width=width)
    try:
        annot.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_OPEN_ARROW)
    except Exception:
        pass
    try:
        annot.set_opacity(opacity)
    except Exception:
        pass
    annot.update()
    return annot


def _fit_font_size(text, width, height, start_size, fontname, lineheight=1.32):
    """先算出能放下的字号，避免"写一半失败再重写"导致文字叠印。"""
    size = float(start_size)
    while size >= 5.0:
        total_lines = 0
        for line in text.split("\n"):
            try:
                line_width = fitz.get_text_length(line, fontname=fontname, fontsize=size)
            except Exception:
                line_width = len(line) * size * 0.6
            total_lines += max(1, int(-(-line_width // max(1.0, width))))
        if total_lines * size * lineheight + 2 <= height:
            return size
        size = round(size * 0.9, 2)
    return 5.0


def add_textbox(page, rect, text, font_size=12, color=(0, 0, 0), fill=None,
                border_color=None, align=0, opacity=1.0):
    """在页面上放一个带底色的文字框。

    这里刻意不用 FreeText 注释：PyMuPDF 生成 FreeText 外观时会忽略填充色，
    首尾字符也容易被裁掉。改为直接画圆角底色 + 写文字，渲染效果稳定。
    代价是它成为页面内容的一部分（可以用撤销撤回），不再作为可拖动注释。
    """
    rect = fitz.Rect(rect)
    rect.normalize()
    if rect.width < 40:
        rect.x1 = rect.x0 + 40
    lines = max(1, text.count("\n") + 1)
    min_height = font_size * 1.6 * lines + 12
    if rect.height < min_height:
        rect.y1 = rect.y0 + min_height

    if fill is not None or border_color is not None:
        width = 1.0 if border_color else 0
        try:
            page.draw_rect(rect, color=border_color, fill=fill, width=width, radius=0.08)
        except TypeError:
            page.draw_rect(rect, color=border_color, fill=fill, width=width)

    inner = fitz.Rect(rect.x0 + 8, rect.y0 + 6, rect.x1 - 8, rect.y1 - 6)
    font = CJK_FONT if _has_cjk(text) else "helv"
    size = _fit_font_size(text, inner.width, inner.height, font_size, font)
    try:
        page.insert_textbox(
            inner, text, fontsize=size, fontname=font, color=color,
            align=align, lineheight=1.32,
        )
    except Exception:
        page.insert_text(fitz.Point(inner.x0, inner.y0 + size), text,
                         fontsize=size, fontname=font, color=color)
    return True


def add_note(page, point, text, color=(1.0, 0.82, 0.25)):
    annot = page.add_text_annot(fitz.Point(point), text, icon="Comment")
    try:
        annot.set_colors(stroke=color)
    except Exception:
        pass
    annot.update()
    return annot


def add_stamp_text(page, rect, text, color, font_size=20, opacity=1.0):
    """在矩形内居中写入图章文字（带边框，写入页面内容）。"""
    return add_textbox(page, rect, text, font_size=font_size, color=color,
                       fill=None, border_color=color, align=1)


# ----------------------------------------------------------------------
# 注释读取 / 命中测试 / 删除
# ----------------------------------------------------------------------
TYPE_NAMES = {
    "Highlight": "高亮",
    "Underline": "下划线",
    "StrikeOut": "删除线",
    "Squiggly": "波浪线",
    "Ink": "手绘",
    "Square": "矩形",
    "Circle": "椭圆",
    "Line": "直线/箭头",
    "FreeText": "文本框",
    "Text": "便签",
    "Stamp": "图章",
}


def list_annotations(doc, index=None):
    """列出注释，index 为 None 时遍历全文。"""
    items = []
    pages = range(doc.page_count) if index is None else [index]
    for pno in pages:
        page = doc.doc[pno]
        try:
            annots = list(page.annots() or [])
        except Exception:
            annots = []
        for annot in annots:
            info = annot.info or {}
            items.append(
                {
                    "page": pno,
                    "xref": annot.xref,
                    "type": annot.type[1] if annot.type else "Annot",
                    "type_cn": TYPE_NAMES.get(annot.type[1] if annot.type else "", "注释"),
                    "content": (info.get("content") or "").strip(),
                    "rect": tuple(annot.rect),
                    "annot": annot,
                }
            )
    return items


def annotation_at(doc, index, point, tolerance=2.0):
    page = doc.doc[index]
    try:
        annots = list(page.annots() or [])
    except Exception:
        return None
    x, y = point
    for annot in annots:
        rect = annot.rect
        if (rect.x0 - tolerance) <= x <= (rect.x1 + tolerance) and (rect.y0 - tolerance) <= y <= (rect.y1 + tolerance):
            return annot
    return None


def delete_annotation(doc, index, xref):
    page = doc.doc[index]
    try:
        for annot in page.annots() or []:
            if annot.xref == xref:
                page.delete_annot(annot)
                return True
    except Exception as exc:
        raise PdfError("删除注释失败：%s" % exc, "annot")
    return False


def update_annotation(doc, index, xref, color=None, opacity=None, width=None, content=None, rect=None):
    page = doc.doc[index]
    for annot in page.annots() or []:
        if annot.xref != xref:
            continue
        if rect is not None:
            annot.set_rect(fitz.Rect(rect))
        if color is not None:
            annot.set_colors(stroke=color)
        if width is not None:
            try:
                annot.set_border(width=width)
            except Exception:
                pass
        if opacity is not None:
            try:
                annot.set_opacity(opacity)
            except Exception:
                pass
        if content is not None:
            annot.set_info(content=content)
        annot.update()
        return True
    return False


def flatten_annotations(doc, pages=None):
    pages = pages if pages is not None else range(doc.page_count)
    for pno in pages:
        page = doc.doc[pno]
        try:
            for annot in list(page.annots() or []):
                annot.update()
        except Exception:
            continue
