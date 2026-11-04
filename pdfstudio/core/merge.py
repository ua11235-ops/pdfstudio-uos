# -*- coding: utf-8 -*-
"""多文档合并：源文件管理 + 任意页序输出。

本模块**不依赖任何 Qt 代码**，可以独立在命令行里测试。

和 pageops.merge_files 的区别：
    merge_files 只是"把几个文件首尾相接"，顺序就是文件顺序；
    这里维护的是一张**页序表**——每个输出位置指向"哪个文件的第几页"，
    所以界面层可以随便拖拽、删除单页，最后按这张表写出文件。
"""

import os
import re
import tempfile

try:  # PyMuPDF >= 1.24 推荐新名字，旧版本只有 fitz
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from .document import PdfError, _replace_with_retry


def natural_key(path):
    """按文件名里的数字大小排序：第2章 排在 第10章 前面。

    资源管理器就是这么排的，用户一次选十几份分卷文件时，
    按字典序排会得到 1, 10, 11, 2, 3 这种明显错的顺序。
    """
    name = os.path.basename(path).lower()
    parts = re.split(r"(\d+)", name)
    # 偶数位是文字、奇数位是数字，位置固定所以 int 与 str 不会混着比
    return [int(part) if part.isdigit() else part for part in parts]


def sort_paths(paths):
    """按自然顺序排列文件路径，并去掉重复项（保持首次出现的位置）。"""
    seen = set()
    unique = []
    for path in paths:
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return sorted(unique, key=natural_key)


class MergeSource(object):
    """一个待合并的源文件。

    打开后保持打开：拖拽排序会反复取页面，每次重新 open 既慢，
    又可能因为文件在合并过程中被别的程序改动而前后不一致。
    """

    def __init__(self, path, password=""):
        self.path = os.path.abspath(path)
        self.password = password
        self._doc = None
        self.page_count = 0
        self.sizes = []  # 每页的 (宽, 高)，用来算缩略图比例

    @property
    def name(self):
        return os.path.basename(self.path)

    @property
    def is_open(self):
        return self._doc is not None

    def open(self):
        if self._doc is not None:
            return self._doc
        if not os.path.isfile(self.path):
            raise PdfError("文件不存在：%s" % self.path, "not_found")
        try:
            doc = fitz.open(self.path)
        except Exception as exc:
            raise PdfError("无法解析《%s》：%s" % (self.name, exc), "parse")
        if doc.needs_pass:
            if not self.password or not doc.authenticate(self.password):
                doc.close()
                raise PdfError("《%s》已加密，需要密码" % self.name, "password")
        if doc.page_count == 0:
            doc.close()
            raise PdfError("《%s》里没有任何页面" % self.name, "empty")
        self._doc = doc
        self.page_count = doc.page_count
        self.sizes = []
        for index in range(self.page_count):
            rect = doc[index].rect
            self.sizes.append((float(rect.width), float(rect.height)))
        return doc

    def page(self, index):
        return self.open()[index]

    def close(self):
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:
                pass
        self._doc = None


class MergePlan(object):
    """合并计划。

    order 是唯一的真相：每一项 (源文件下标, 源文件内的页码)。
    拖拽排序、删除单页都只改这张表，源文件本身一个字节都不动，
    所以反复调整顺序不会累积质量损失，也不需要撤销栈。
    """

    def __init__(self):
        self.sources = []
        self.order = []

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------
    @property
    def total_pages(self):
        return len(self.order)

    @property
    def file_count(self):
        return len(self.sources)

    def kept_pages(self, source_index):
        """某个源文件还有多少页留在结果里。"""
        return sum(1 for src, _page in self.order if src == source_index)

    def position_of(self, key):
        """(源, 页) 在输出里的位置，找不到返回 -1。"""
        try:
            return self.order.index(key)
        except ValueError:
            return -1

    # ------------------------------------------------------------------
    # 源文件
    # ------------------------------------------------------------------
    def add_source(self, path, password=""):
        """添加一个源文件，返回它在 sources 里的下标。

        同一个文件允许添加多次——用户有时确实想把某份内容重复放两遍，
        去重反而挡住了正常用法。真正需要去重的是"一次选中里重复"，
        那个在 sort_paths 里做掉了。
        """
        source = MergeSource(path, password)
        source.open()  # 加密 / 损坏 / 空文件在这里就暴露，不要等到最后写文件才报
        index = len(self.sources)
        self.sources.append(source)
        for page in range(source.page_count):
            self.order.append((index, page))
        return index

    def remove_source(self, index):
        """移除一个源文件及其所有页，返回被移除的页数。"""
        if not (0 <= index < len(self.sources)):
            return 0
        kept = [item for item in self.order if item[0] != index]
        removed = len(self.order) - len(kept)
        # 后面的源下标整体前移一位，否则会指向错的文件
        self.order = [((src - 1 if src > index else src), page) for src, page in kept]
        self.sources[index].close()
        del self.sources[index]
        return removed

    # ------------------------------------------------------------------
    # 页序
    # ------------------------------------------------------------------
    def set_order(self, keys):
        """按 keys 重排（界面拖拽结束后调用）。

        keys 必须正好是当前页序的一个排列：漏页或重复都说明界面状态和模型
        已经不同步了，这时候继续写文件会静默丢页，宁可报错。
        """
        keys = list(keys)
        if sorted(keys) != sorted(self.order):
            raise PdfError("页序不一致，请重新打开合并窗口", "order")
        self.order = keys

    def drop_pages(self, positions):
        """删除输出里的若干位置，返回实际删除的页数。"""
        targets = sorted({p for p in positions if 0 <= p < len(self.order)}, reverse=True)
        for position in targets:
            del self.order[position]
        return len(targets)

    def move_page(self, position, target):
        """把第 position 页挪到 target 位置（拖拽的模型层等价操作）。"""
        if not (0 <= position < len(self.order)):
            return
        target = max(0, min(target, len(self.order) - 1))
        if target == position:
            return
        item = self.order.pop(position)
        self.order.insert(target, item)

    def clear(self):
        for source in self.sources:
            source.close()
        self.sources = []
        self.order = []

    def close(self):
        self.clear()

    # ------------------------------------------------------------------
    # 输出
    # ------------------------------------------------------------------
    def build(self, out_path, progress=None):
        """按页序写出合并结果，返回输出路径。

        progress(已完成页数, 总页数) 可选，用来驱动进度条。
        """
        if not self.order:
            raise PdfError("还没有可以合并的页面", "empty")
        folder = os.path.dirname(os.path.abspath(out_path))
        if folder and not os.path.isdir(folder):
            raise PdfError("保存目录不存在：%s" % folder, "no_dir")
        # 提前探一下权限，比让 mkstemp 抛 "[Errno 13] Permission denied" 好懂
        if not os.access(folder or ".", os.W_OK):
            raise PdfError(
                "没有写入权限：%s\n换个位置保存试试（比如桌面或文档目录）。" % folder,
                "no_write")

        out = fitz.open()
        done = 0
        total = len(self.order)
        try:
            for src_index, from_page, to_page in _runs(self.order):
                source = self.sources[src_index]
                out.insert_pdf(source.open(), from_page=from_page, to_page=to_page)
                done += to_page - from_page + 1
                if progress is not None:
                    progress(done, total)
            _save_atomic(out, out_path)
        except PdfError:
            raise
        except Exception as exc:
            raise PdfError("合并失败：%s" % exc, "merge")
        finally:
            try:
                out.close()
            except Exception:
                pass
        return out_path


def _runs(order):
    """把页序压成连续区间 [(源, 起始页, 结束页), ...]。

    一次 insert_pdf 拷一页，几千页就是几千次调用；压成区间后通常只剩几次。
    拖拽打乱的只是少数几页，压完依然是大段的。
    """
    runs = []
    for src, page in order:
        if runs and runs[-1][0] == src and runs[-1][2] == page - 1:
            runs[-1] = (src, runs[-1][1], page)
        else:
            runs.append((src, page, page))
    return runs


def _save_atomic(doc, out_path):
    """先写临时文件再替换，避免写一半失败把用户原有的文件毁掉。

    覆盖同名文件是常见操作（"再合并一次"），而 fitz 直接 save 到已存在
    的路径是先截断再写，中途出错就只剩个空文件。
    """
    folder = os.path.dirname(os.path.abspath(out_path)) or "."
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=folder)
    os.close(fd)
    try:
        doc.save(tmp, garbage=3, deflate=True)
        _replace_with_retry(tmp, out_path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def default_output_name(sources, folder=None):
    """给合并结果起个默认文件名：取第一个文件的名字加"_合并"。"""
    folder = folder or os.path.expanduser("~")
    if sources:
        base = os.path.splitext(os.path.basename(sources[0].path))[0]
        name = base + "_合并.pdf"
    else:
        name = "合并结果.pdf"
    return os.path.join(folder, name)
