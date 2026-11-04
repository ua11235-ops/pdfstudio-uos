# -*- coding: utf-8 -*-
"""安全相关：加密、解密、涂黑脱敏。"""

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from .document import PdfError


PERM_PRINT = 4
PERM_MODIFY = 8
PERM_COPY = 16
PERM_ANNOTATE = 32
PERM_FORM = 256
PERM_ACCESSIBILITY = 512
PERM_ASSEMBLE = 1024
PERM_PRINT_HQ = 2048


def build_permissions(allow_print=True, allow_copy=False, allow_modify=False,
                      allow_annotate=True, allow_form=True):
    perms = PERM_ACCESSIBILITY
    if allow_print:
        perms |= PERM_PRINT | PERM_PRINT_HQ
    if allow_copy:
        perms |= PERM_COPY
    if allow_modify:
        perms |= PERM_MODIFY | PERM_ASSEMBLE
    if allow_annotate:
        perms |= PERM_ANNOTATE
    if allow_form:
        perms |= PERM_FORM
    return perms


def encrypt_to(doc, out_path, user_password, owner_password=None,
               allow_print=True, allow_copy=False, allow_modify=False,
               allow_annotate=True, allow_form=True):
    """另存为加密副本（不改变当前内存文档的密码状态）。"""
    if not user_password:
        raise PdfError("请设置打开密码", "password")
    perms = build_permissions(allow_print, allow_copy, allow_modify, allow_annotate, allow_form)
    try:
        doc.doc.save(
            out_path,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw=owner_password or user_password,
            user_pw=user_password,
            permissions=perms,
            garbage=3,
            deflate=True,
        )
    except Exception as exc:
        raise PdfError("加密保存失败：%s" % exc, "encrypt")
    return out_path


def decrypt_to(doc, out_path):
    """另存为无密码副本。文档必须已经通过密码验证。"""
    try:
        doc.doc.save(out_path, encryption=fitz.PDF_ENCRYPT_NONE, garbage=3, deflate=True)
    except Exception as exc:
        raise PdfError("解密保存失败：%s" % exc, "decrypt")
    return out_path


def redact_areas(doc, areas, fill=(0, 0, 0)):
    """areas: [(page_index, (x0, y0, x1, y1)), ...]，执行真正的涂黑。"""
    by_page = {}
    for page_index, rect in areas:
        by_page.setdefault(page_index, []).append(rect)
    count = 0
    for page_index, rects in by_page.items():
        page = doc.doc[page_index]
        for rect in rects:
            page.add_redact_annot(fitz.Rect(rect), fill=fill)
            count += 1
        try:
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )
        except TypeError:
            page.apply_redactions()
    return count


def redact_text(doc, text, pages=None, fill=(0, 0, 0)):
    """按文字内容涂黑，返回处理次数。"""
    targets = pages if pages is not None else range(doc.page_count)
    count = 0
    for page_index in targets:
        page = doc.doc[page_index]
        hits = page.search_for(text)
        if not hits:
            continue
        for rect in hits:
            page.add_redact_annot(fitz.Rect(rect), fill=fill)
            count += 1
        try:
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )
        except TypeError:
            page.apply_redactions()
    return count


def redact_regex(doc, pattern, pages=None, fill=(0, 0, 0)):
    import re

    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise PdfError("正则表达式无效：%s" % exc, "regex")
    targets = pages if pages is not None else range(doc.page_count)
    count = 0
    for page_index in targets:
        page = doc.doc[page_index]
        words = doc.page_words(page_index)
        matched = [w for w in words if regex.search(w[4])]
        if not matched:
            continue
        for word in matched:
            page.add_redact_annot(fitz.Rect(word[:4]), fill=fill)
            count += 1
        try:
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )
        except TypeError:
            page.apply_redactions()
    return count


def remove_metadata(doc):
    doc.doc.set_metadata(
        {
            "title": "",
            "author": "",
            "subject": "",
            "keywords": "",
            "creator": "PDF Studio",
            "producer": "PDF Studio",
        }
    )
