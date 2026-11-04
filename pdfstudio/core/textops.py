# -*- coding: utf-8 -*-
"""文本层编辑：替换页面上的文字、插入新文字。

原理：先用 redact 精确擦除目标区域的文字（保留图片与矢量图形），
再在相同位置写入新文本，从而做到"像 Word 一样改 PDF 里的字"。
"""

import re

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from .document import PdfError
from .annotate import CJK_FONT

CJK_RE = re.compile(u"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uffef]")


def has_cjk(text):
    return bool(CJK_RE.search(text or ""))


def int_to_rgb(value):
    value = int(value or 0)
    return (
        ((value >> 16) & 0xFF) / 255.0,
        ((value >> 8) & 0xFF) / 255.0,
        (value & 0xFF) / 255.0,
    )


def rgb_to_int(color):
    r, g, b = [max(0, min(255, int(round(c * 255)))) for c in color]
    return (r << 16) | (g << 8) | b


def _apply_redactions_soft(page):
    """只擦除文字，不动图片和线条，避免误删页面图形。"""
    try:
        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_NONE,
            graphics=fitz.PDF_REDACT_LINE_ART_NONE,
            text=fitz.PDF_REDACT_TEXT_REMOVE,
        )
    except TypeError:
        page.apply_redactions()
    except Exception as exc:
        raise PdfError("擦除文字失败：%s" % exc, "redact")


def replace_span_text(page, span, new_text, fill=(1, 1, 1), font_size=None,
                      color=None, align=0):
    """把 span 上的文字替换为 new_text，尽量保持原字号与颜色。"""
    rect = fitz.Rect(span["bbox"])
    size = float(font_size or span.get("size") or 12)
    rgb = color or int_to_rgb(span.get("color", 0))

    pad = fitz.Rect(rect.x0 - 1, rect.y0 - 1, rect.x1 + 1, rect.y1 + 1)
    page.add_redact_annot(pad, fill=fill)
    _apply_redactions_soft(page)

    if not new_text:
        return True

    font = CJK_FONT if has_cjk(new_text) else "helv"
    box = fitz.Rect(rect.x0, rect.y0 - size * 0.35, max(rect.x1, rect.x0 + 40), rect.y1 + size * 0.6)
    try:
        spare, _ = page.insert_textbox(
            box, new_text, fontsize=size, fontname=font, color=rgb, align=align
        )
        if spare >= 0:
            return True
    except Exception:
        pass
    # 文本框放不下时退化为单行写入
    baseline = fitz.Point(rect.x0, rect.y1 - size * 0.22)
    page.insert_text(baseline, new_text, fontsize=size, fontname=font, color=rgb)
    return True


def replace_all(page, find, replace, fill=(1, 1, 1), color=None):
    """在整页范围内批量替换文字。返回替换次数。"""
    hits = page.search_for(find)
    if not hits:
        return 0
    for rect in hits:
        page.add_redact_annot(fitz.Rect(rect.x0 - 1, rect.y0 - 1, rect.x1 + 1, rect.y1 + 1), fill=fill)
    _apply_redactions_soft(page)
    for rect in hits:
        size = max(6.0, min(rect.height * 0.85, 48))
        font = CJK_FONT if has_cjk(replace) else "helv"
        page.insert_text(
            fitz.Point(rect.x0, rect.y1 - size * 0.22),
            replace,
            fontsize=size,
            fontname=font,
            color=color or (0, 0, 0),
        )
    return len(hits)


def insert_text(page, point, text, font_size=14, color=(0, 0, 0), align=0,
                max_width=0, line_height=1.35):
    """在指定位置插入新文字，支持多行与自动换行。"""
    font = CJK_FONT if has_cjk(text) else "helv"
    x, y = point
    if max_width and max_width > 20:
        box = fitz.Rect(x, y, x + max_width, y + max(60, len(text) * font_size * 2))
        try:
            spare, _ = page.insert_textbox(
                box, text, fontsize=font_size, fontname=font, color=color,
                align=align, lineheight=line_height,
            )
            if spare >= 0:
                return True
        except Exception:
            pass
    page.insert_text(fitz.Point(x, y), text, fontsize=font_size, fontname=font, color=color)
    return True


def page_background_color(page):
    """粗略判断页面底色，用于擦除时选择填充色。"""
    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(0.15, 0.15), alpha=False)
        if pix.n >= 3:
            samples = pix.samples
            n = len(samples) // 3
            if n == 0:
                return (1, 1, 1)
            step = max(1, n // 500)
            total = [0, 0, 0]
            count = 0
            for i in range(0, n, step):
                total[0] += samples[i * 3]
                total[1] += samples[i * 3 + 1]
                total[2] += samples[i * 3 + 2]
                count += 1
            if count:
                avg = [t / float(count) / 255.0 for t in total]
                if min(avg) > 0.93:
                    return (1, 1, 1)
                return tuple(round(c, 3) for c in avg)
    except Exception:
        pass
    return (1, 1, 1)


def ocr_page_text(page, lang="chi_sim+eng"):
    """对扫描件做 OCR，返回文字。需要系统安装 tesseract。"""
    try:
        tp = page.get_textpage_ocr(language=lang, dpi=200, full=True)
        return page.get_text(textpage=tp)
    except Exception as exc:
        raise PdfError(
            "OCR 不可用，请先安装 tesseract-ocr 与中文语言包（%s）" % exc, "ocr"
        )
