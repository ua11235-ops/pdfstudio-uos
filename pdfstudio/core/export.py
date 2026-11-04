# -*- coding: utf-8 -*-
"""导出与压缩。"""

import os

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from .document import PdfError


def compress_to(doc, out_path, level="standard", dpi=150, quality=75):
    """压缩另存。

    level=standard：清理冗余对象、压缩流、字体子集化（无损，速度较快）
    level=strong  ：把每页重新栅格化为 JPEG 再组包（有损，扫描件效果最好）
    """
    if level == "strong":
        return _rasterize_to(doc, out_path, dpi=dpi, quality=quality)
    try:
        doc.doc.save(
            out_path,
            garbage=4,
            deflate=True,
            deflate_images=True,
            deflate_fonts=True,
            clean=True,
        )
    except Exception as exc:
        raise PdfError("压缩失败：%s" % exc, "compress")
    return out_path


def _rasterize_to(doc, out_path, dpi=150, quality=75):
    out = fitz.open()
    try:
        for index in range(doc.page_count):
            page = doc.doc[index]
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            data = pix.tobytes("jpeg", jpg_quality=quality)
            rect = page.rect
            new_page = out.new_page(width=rect.width, height=rect.height)
            new_page.insert_image(new_page.rect, stream=data)
        out.save(out_path, garbage=4, deflate=True, clean=True)
    except Exception as exc:
        raise PdfError("压缩失败：%s" % exc, "compress")
    finally:
        out.close()
    return out_path


def to_long_image(doc, out_path, pages=None, dpi=120, gap=0, max_width=2400):
    """把多页纵向拼成一张长图（适合聊天 / 微信发送）。"""
    targets = list(pages) if pages is not None else list(range(doc.page_count))
    if not targets:
        raise PdfError("没有可导出的页面", "no_pages")

    images = []
    for index in targets:
        page = doc.doc[index]
        zoom = dpi / 72.0
        if max_width and page.rect.width * zoom > max_width:
            zoom = max_width / float(page.rect.width)
        images.append(page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False))

    width = max(pix.width for pix in images)
    height = sum(pix.height for pix in images) + gap * (len(images) - 1)
    canvas = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height), False)
    canvas.set_rect(canvas.irect, (255, 255, 255))
    y = 0
    for pix in images:
        target = fitz.IRect(0, y, pix.width, y + pix.height)
        try:
            canvas.copy(pix, pix.irect, target)
        except Exception:
            pass
        y += pix.height + gap
    canvas.save(out_path)
    return out_path


def file_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def human_size(num):
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            if unit == "B":
                return "%d %s" % (num, unit)
            return "%.1f %s" % (num, unit)
        num /= 1024.0
    return "%d B" % num
