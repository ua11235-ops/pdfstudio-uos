# -*- coding: utf-8 -*-
"""页面级操作：插入、删除、旋转、移动、提取、拆分、合并。"""

import os

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from .document import PdfError


def _normalize(indices, count):
    out = []
    for i in indices:
        if 0 <= i < count and i not in out:
            out.append(i)
    return sorted(out)


def insert_blank_page(doc, index, width=None, height=None):
    """在 index 位置插入一页空白页。"""
    d = doc.doc
    if d.page_count == 0:
        d.new_page(width=width or 595, height=height or 842)
        return
    ref = d[min(index, d.page_count - 1)]
    w = width or ref.rect.width
    h = height or ref.rect.height
    d.new_page(pno=min(index, d.page_count), width=w, height=h)


def insert_from_file(doc, src_path, index, from_page=0, to_page=None, password=""):
    """把另一个 PDF 的页面插入到 index 位置。"""
    if not os.path.isfile(src_path):
        raise PdfError("找不到要插入的文件：%s" % src_path, "not_found")
    try:
        src = fitz.open(src_path)
    except Exception as exc:
        raise PdfError("无法打开插入源：%s" % exc, "parse")
    if src.needs_pass:
        if not password or not src.authenticate(password):
            src.close()
            raise PdfError("插入源文件已加密，需要密码", "password")
    if to_page is None:
        to_page = src.page_count - 1
    try:
        doc.doc.insert_pdf(src, from_page=from_page, to_page=to_page, start_at=index)
    finally:
        src.close()


def delete_pages(doc, indices):
    d = doc.doc
    targets = _normalize(indices, d.page_count)
    if not targets:
        return 0
    if len(targets) >= d.page_count:
        raise PdfError("不能删除全部页面，至少保留一页", "last_page")
    for idx in reversed(targets):
        d.delete_page(idx)
    return len(targets)


def rotate_pages(doc, indices, angle):
    d = doc.doc
    targets = _normalize(indices, d.page_count) or list(range(d.page_count))
    for idx in targets:
        page = d[idx]
        page.set_rotation((page.rotation + angle) % 360)


def set_page_rotation(doc, index, angle):
    doc.doc[index].set_rotation(angle % 360)


def move_page(doc, src, dst):
    d = doc.doc
    if src == dst:
        return
    if not (0 <= src < d.page_count):
        return
    dst = max(0, min(dst, d.page_count - 1))
    order = list(range(d.page_count))
    order.insert(dst, order.pop(src))
    reorder_pages(doc, order)


def reorder_pages(doc, order):
    """按 order 重排页面。

    PyMuPDF 的 move_page 在部分版本上对相邻页无效，这里统一用 select 实现，
    行为稳定且一次调用即可完成任意重排。
    """
    if sorted(order) != list(range(doc.page_count)):
        raise PdfError("页面顺序不完整", "reorder")
    doc.doc.select(list(order))


def extract_pages(doc, indices, out_path):
    d = doc.doc
    targets = _normalize(indices, d.page_count)
    if not targets:
        raise PdfError("请先选择要提取的页面", "no_selection")
    out = fitz.open()
    for idx in targets:
        out.insert_pdf(d, from_page=idx, to_page=idx)
    out.save(out_path, garbage=3, deflate=True)
    out.close()
    return out_path


def split_by_ranges(doc, out_dir, ranges, prefix=None):
    """按 [(start, end), ...]（含两端、从 0 开始）拆分。"""
    d = doc.doc
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    base = prefix or os.path.splitext(os.path.basename(doc.path or "document"))[0]
    written = []
    for order, (start, end) in enumerate(ranges, 1):
        start = max(0, start)
        end = min(d.page_count - 1, end)
        if end < start:
            continue
        out = fitz.open()
        out.insert_pdf(d, from_page=start, to_page=end)
        name = "%s_%02d_p%d-%d.pdf" % (base, order, start + 1, end + 1)
        full = os.path.join(out_dir, name)
        out.save(full, garbage=3, deflate=True)
        out.close()
        written.append(full)
    return written


def split_each_page(doc, out_dir, prefix=None):
    ranges = [(i, i) for i in range(doc.page_count)]
    return split_by_ranges(doc, out_dir, ranges, prefix)


def merge_files(paths, out_path, passwords=None):
    out = fitz.open()
    passwords = passwords or {}
    for path in paths:
        src = fitz.open(path)
        if src.needs_pass:
            pwd = passwords.get(path, "")
            if not pwd or not src.authenticate(pwd):
                src.close()
                raise PdfError("文件已加密，需要密码：%s" % os.path.basename(path), "password")
        out.insert_pdf(src)
        src.close()
    out.save(out_path, garbage=3, deflate=True)
    out.close()
    return out_path


def page_labels(doc):
    labels = []
    for idx in range(doc.page_count):
        try:
            labels.append(doc.doc[idx].get_label() or str(idx + 1))
        except Exception:
            labels.append(str(idx + 1))
    return labels
