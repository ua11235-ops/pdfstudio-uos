# -*- coding: utf-8 -*-
"""PDF 文档核心模型。

本模块**不依赖任何 Qt 代码**，可以独立在命令行里测试。
界面层只通过公开方法访问文档，所有修改都经过 begin_change / end_change
形成可撤销的快照，避免直接操作 PyMuPDF 对象导致状态不一致。
"""

from __future__ import print_function

import os
import shutil
import tempfile
import time

try:  # PyMuPDF >= 1.24 推荐新名字，旧版本只有 fitz
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz


MAX_UNDO_STEPS = 30
MAX_UNDO_BYTES = 480 * 1024 * 1024


class PdfError(Exception):
    """文档操作异常。code 用于界面层给出更友好的提示。"""

    def __init__(self, message, code=None):
        Exception.__init__(self, message)
        self.code = code or "generic"


def _replace_with_retry(src, dst, attempts=6, delay=0.12):
    """用临时文件替换原文件，替换失败时重试几次。

    Windows 上目标文件被别的程序打开着（比如另一个 PDF 阅读器、
    网盘同步、杀软扫描）时，替换会直接抛"拒绝访问"。这种情况下
    隔一两百毫秒再试往往就成功了，比让用户看到一句英文报错好得多。
    """
    last = None
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except OSError as exc:
            last = exc
            if i == attempts - 1:
                break
            time.sleep(delay)
    raise PdfError(
        "无法写入《%s》，它可能正被其他程序打开（比如另一个阅读器或网盘同步）。\n"
        "请关闭后再试，或用「另存为」存到别的文件名。（%s）"
        % (os.path.basename(dst), last),
        "locked")


class PdfDocument(object):
    """单个 PDF 文件的内存模型。"""

    def __init__(self):
        self._doc = None
        self.path = ""
        self.password = ""
        self.page_index = 0
        self.revision = 0
        self.dirty = False
        self._encryption = None  # 保存时沿用的加密参数
        self._undo = []          # [(label, bytes, page_index)]
        self._redo = []
        self._listeners = []
        self._cache = {}         # 渲染缓存 {(page, zoom_key, revision): pixmap}

    # ------------------------------------------------------------------
    # 基础状态
    # ------------------------------------------------------------------
    @property
    def is_open(self):
        return self._doc is not None

    @property
    def doc(self):
        if self._doc is None:
            raise PdfError("尚未打开任何文档", "no_document")
        return self._doc

    @property
    def page_count(self):
        return self._doc.page_count if self._doc is not None else 0

    @property
    def title(self):
        if self._doc is None:
            return ""
        meta = self._doc.metadata or {}
        name = (meta.get("title") or "").strip()
        if name:
            return name
        return os.path.splitext(os.path.basename(self.path))[0]

    @property
    def display_name(self):
        if not self.path:
            return "未命名"
        return os.path.basename(self.path)

    # ------------------------------------------------------------------
    # 观察者（界面刷新）
    # ------------------------------------------------------------------
    def add_listener(self, callback):
        self._listeners.append(callback)

    def notify(self, what="change"):
        for cb in list(self._listeners):
            try:
                cb(what)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 打开 / 关闭 / 保存
    # ------------------------------------------------------------------
    def open(self, path, password=""):
        if not os.path.isfile(path):
            raise PdfError("文件不存在：%s" % path, "not_found")
        try:
            doc = fitz.open(path)
        except Exception as exc:
            raise PdfError("无法解析该 PDF：%s" % exc, "parse")
        if doc.needs_pass:
            ok = bool(password) and doc.authenticate(password)
            if not ok:
                doc.close()
                raise PdfError("文档已加密，需要密码", "password")
        self._doc = doc
        self.path = os.path.abspath(path)
        self.password = password
        self.page_index = 0
        self.dirty = False
        self._undo = []
        self._redo = []
        self._cache = {}
        self._encryption = self._detect_encryption(doc)
        self.revision += 1
        self.notify("open")
        return True

    def close(self):
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:
                pass
        self._doc = None
        self.path = ""
        self.page_index = 0
        self.dirty = False
        self._undo = []
        self._redo = []
        self._cache = {}
        self._encryption = None
        self.revision += 1
        self.notify("close")

    def _detect_encryption(self, doc):
        """已加密文档保存时保持原有加密，避免"另存为"后密码失效。"""
        try:
            if doc.is_encrypted and doc.metadata is not None:
                if doc.permissions is not None and self.password:
                    return {
                        "user_pw": self.password,
                        "owner_pw": self.password,
                        "permissions": int(doc.permissions),
                    }
        except Exception:
            pass
        return None

    def save(self, path=None, encryption=None):
        """保存文档。同一路径时先写临时文件再原子替换，避免写坏原文件。"""
        if self._doc is None:
            raise PdfError("尚未打开任何文档", "no_document")
        target = path or self.path
        if not target:
            raise PdfError("未指定保存路径", "no_path")
        target = os.path.abspath(target)
        same = os.path.abspath(self.path) == target
        enc = encryption if encryption is not None else self._encryption

        save_kw = dict(garbage=3, deflate=True, deflate_images=True, deflate_fonts=True)
        if enc:
            save_kw.update(
                encryption=fitz.PDF_ENCRYPT_AES_256,
                owner_pw=enc.get("owner_pw") or enc.get("user_pw") or "",
                user_pw=enc.get("user_pw") or "",
                permissions=int(enc.get("permissions", -1)),
            )

        try:
            if same:
                folder = os.path.dirname(target) or "."
                fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=folder)
                os.close(fd)
                try:
                    self._doc.save(tmp, **save_kw)
                    self._doc.close()
                    _replace_with_retry(tmp, target)
                except Exception:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                    raise
            else:
                self._doc.save(target, **save_kw)
                self._doc.close()
        except Exception as exc:
            # 保存失败后重新打开原文件，保证后续操作还能继续
            try:
                self._doc = fitz.open(self.path)
                if self.password and self._doc.needs_pass:
                    self._doc.authenticate(self.password)
            except Exception:
                self._doc = None
            # 文件被占用时抛出的提示是给人看的，别再用"保存失败"包一层
            if isinstance(exc, PdfError):
                raise
            raise PdfError("保存失败：%s" % exc, "save")

        self._doc = fitz.open(target)
        if self._doc.needs_pass and self.password:
            self._doc.authenticate(self.password)
        self.path = target
        if enc:
            self._encryption = enc
        self.dirty = False
        self._cache = {}
        self.revision += 1
        self.notify("saved")
        return target

    # ------------------------------------------------------------------
    # 撤销 / 重做（基于整份文档快照，简单可靠）
    # ------------------------------------------------------------------
    def begin_change(self, label="编辑"):
        if self._doc is None:
            return
        data = self._doc.tobytes(garbage=0, deflate=True)
        self._undo.append((label, data, self.page_index))
        self._redo = []
        self._trim_undo()

    def end_change(self, label=None):
        if self._doc is None:
            return
        self.dirty = True
        self._cache = {}
        self.revision += 1
        self.notify("change")

    def _trim_undo(self):
        total = sum(len(item[1]) for item in self._undo)
        while len(self._undo) > MAX_UNDO_STEPS or (total > MAX_UNDO_BYTES and len(self._undo) > 3):
            _label, data, _idx = self._undo.pop(0)
            total -= len(data)

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def undo_label(self):
        return self._undo[-1][0] if self._undo else ""

    def redo_label(self):
        return self._redo[-1][0] if self._redo else ""

    def _load_snapshot(self, data, page_index):
        doc = fitz.open("pdf", data)
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:
                pass
        self._doc = doc
        self.page_index = max(0, min(page_index, max(0, doc.page_count - 1)))
        self._cache = {}
        self.revision += 1

    def undo(self):
        if not self._undo:
            return False
        label, data, page = self._undo.pop()
        self._redo.append((label, self._doc.tobytes(garbage=0, deflate=True), self.page_index))
        self._load_snapshot(data, page)
        self.dirty = True
        self.notify("change")
        return True

    def redo(self):
        if not self._redo:
            return False
        label, data, page = self._redo.pop()
        self._undo.append((label, self._doc.tobytes(garbage=0, deflate=True), self.page_index))
        self._load_snapshot(data, page)
        self.dirty = True
        self.notify("change")
        return True

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------
    def page_size(self, index):
        page = self.doc[index]
        rect = page.rect
        return rect.width, rect.height

    def render(self, index, zoom=1.0, dpi_scale=1.0):
        """返回 (samples, width, height, stride, zoom_used)。

        zoom_key 参与缓存，避免同分辨率反复重新栅格化。
        """
        key = (index, round(zoom, 3), round(dpi_scale, 2), self.revision)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        page = self.doc[index]
        matrix = fitz.Matrix(zoom * dpi_scale, zoom * dpi_scale)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        result = (pix.samples, pix.width, pix.height, pix.stride, zoom * dpi_scale)
        if len(self._cache) > 24:
            self._cache.clear()
        self._cache[key] = result
        return result

    def clear_cache(self):
        self._cache = {}

    # ------------------------------------------------------------------
    # 文本 / 搜索
    # ------------------------------------------------------------------
    def page_text(self, index):
        return self.doc[index].get_text("text")

    def page_spans(self, index):
        """返回页面上所有文本片段，供"编辑文字"使用。"""
        page = self.doc[index]
        spans = []
        try:
            data = page.get_text("dict")
        except Exception:
            return spans
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text.strip():
                        continue
                    spans.append(
                        {
                            "bbox": tuple(span["bbox"]),
                            "text": text,
                            "size": float(span.get("size", 12)),
                            "font": span.get("font", ""),
                            "color": int(span.get("color", 0)),
                        }
                    )
        return spans

    def span_at(self, index, point):
        x, y = point
        for span in self.page_spans(index):
            x0, y0, x1, y1 = span["bbox"]
            if x0 - 2 <= x <= x1 + 2 and y0 - 2 <= y <= y1 + 2:
                return span
        return None

    def search(self, text, start_page=0, case_sensitive=False, whole_page=False):
        """全文搜索，返回 [(page_index, rect), ...]。

        中文 PDF 的文字层经常被拆成"统 信 U O S"这样的碎片，
        直接搜 "统信UOS" 会落空，因此每页先精确搜索，失败后再做
        忽略空白 / 大小写的字符级容错搜索。
        """
        results = []
        if not text:
            return results
        total = self.page_count
        order = list(range(start_page, total)) + list(range(0, start_page))
        for idx in order:
            page = self.doc[idx]
            hits = []
            try:
                hits = page.search_for(text)
            except Exception:
                hits = []
            if not hits:
                hits = self._search_normalized_page(page, text, case_sensitive)
            for rect in hits:
                results.append((idx, tuple(rect)))
        return results

    def _page_chars(self, page):
        """逐字符提取，用于容错搜索。"""
        chars = []
        try:
            raw = page.get_text("rawdict")
        except Exception:
            return chars
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    for ch in span.get("chars", []):
                        c = ch.get("c", "")
                        if not c or c.isspace():
                            continue
                        chars.append((c, fitz.Rect(ch["bbox"])))
        return chars

    def _search_normalized_page(self, page, needle, case_sensitive=False):
        chars = self._page_chars(page)
        if not chars:
            return []
        target = "".join(needle.split())
        if not target:
            return []
        stream = "".join(c for c, _ in chars)
        if not case_sensitive:
            target = target.lower()
            stream = stream.lower()
        out = []
        start = 0
        while True:
            pos = stream.find(target, start)
            if pos < 0:
                break
            merged = []
            for i in range(pos, pos + len(target)):
                r = fitz.Rect(chars[i][1])
                if merged and abs(r.y0 - merged[-1].y0) < 3 and r.x0 <= merged[-1].x1 + 3:
                    merged[-1] = fitz.Rect(merged[-1]) | r
                else:
                    merged.append(r)
            out.extend(merged)
            start = pos + len(target)
        return out

    def page_words(self, index, clip=None):
        page = self.doc[index]
        try:
            if clip is not None:
                return page.get_text("words", clip=clip)
            return page.get_text("words")
        except Exception:
            return []

    def text_in_rect(self, index, rect):
        """取矩形内的文字。中文之间不补空格，英文单词之间保留空格。"""
        words = self.page_words(index, clip=rect)
        words.sort(key=lambda w: (round(w[1], 1), w[0]))
        out = []
        prev = None
        for w in words:
            token = w[4]
            if prev is not None:
                gap = w[0] - prev[2]
                ascii_pair = (prev[4][-1:].isascii() and token[:1].isascii()
                              and prev[4][-1:].isalnum() and token[:1].isalnum())
                if gap > max(1.5, (prev[3] - prev[1]) * 0.18) or ascii_pair:
                    out.append(" ")
            out.append(token)
            prev = w
        return "".join(out)

    # ------------------------------------------------------------------
    # 大纲 / 元数据 / 表单
    # ------------------------------------------------------------------
    def outline(self):
        try:
            toc = self.doc.get_toc(simple=True)
        except Exception:
            return []
        return toc or []

    def set_outline(self, toc):
        try:
            self.doc.set_toc(toc)
        except Exception as exc:
            raise PdfError("写入目录失败：%s" % exc, "toc")

    def metadata(self):
        try:
            return dict(self.doc.metadata or {})
        except Exception:
            return {}

    def set_metadata(self, values):
        meta = self.metadata()
        meta.update(values)
        self.doc.set_metadata(meta)

    def widgets(self, index):
        page = self.doc[index]
        items = []
        try:
            for widget in page.widgets():
                items.append(
                    {
                        "name": widget.field_name,
                        "type": widget.field_type_string,
                        "value": widget.field_value,
                        "rect": tuple(widget.rect),
                        "widget": widget,
                    }
                )
        except Exception:
            pass
        return items

    # ------------------------------------------------------------------
    # 打印辅助
    # ------------------------------------------------------------------
    def page_pixmap_for_print(self, index, dpi=200):
        page = self.doc[index]
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pix

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------
    def export_images(self, out_dir, pages=None, dpi=150, fmt="png"):
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        pages = pages if pages is not None else range(self.page_count)
        written = []
        for idx in pages:
            if idx < 0 or idx >= self.page_count:
                continue
            pix = self.doc[idx].get_pixmap(dpi=dpi, alpha=False)
            name = "page_%03d.%s" % (idx + 1, fmt)
            full = os.path.join(out_dir, name)
            pix.save(full)
            written.append(full)
        return written

    def export_text(self, out_path, pages=None):
        pages = pages if pages is not None else range(self.page_count)
        chunks = []
        for idx in pages:
            if 0 <= idx < self.page_count:
                chunks.append("===== 第 %d 页 =====\n%s" % (idx + 1, self.page_text(idx)))
        data = "\n".join(chunks)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(data)
        return out_path
