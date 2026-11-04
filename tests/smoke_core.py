# -*- coding: utf-8 -*-
"""核心层自测：不依赖 Qt，直接验证 PDF 读写与各类编辑操作。"""

import os
import re
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from pdfstudio.core.document import PdfDocument, PdfError
from pdfstudio.core import annotate, decorate, pageops, security, textops, export
from pdfstudio.core import merge as merge_mod

# 样例源文件放在 samples/，测试产物统一丢进 samples/_out，避免污染目录
SAMPLE_DIR = os.path.join(ROOT, "samples")
OUT = os.path.join(SAMPLE_DIR, "_out")
os.makedirs(OUT, exist_ok=True)

PASS = []
FAIL = []


def norm(text):
    """去掉所有空白，规避中文文字层被拆出空格的问题。"""
    return re.sub(r"\s+", "", text or "")


def check(name, fn):
    try:
        fn()
        PASS.append(name)
        print("  [ok] %s" % name)
    except Exception as exc:
        FAIL.append((name, exc))
        print("  [FAIL] %s -> %r" % (name, exc))
        traceback.print_exc()


def make_sample(path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 90), u"PDF Studio 测试文档", fontsize=24, fontname="china-s")
    page.insert_text((72, 130), u"这是一段用于验证文本编辑的示例文字。", fontsize=13, fontname="china-s")
    page.insert_text((72, 160), u"Hello world, this is a test sentence.", fontsize=13, fontname="helv")
    for i in range(18):
        page.insert_text((72, 200 + i * 24), u"第 %d 行内容 —— 统信 UOS 测试数据。" % (i + 1),
                         fontsize=11, fontname="china-s")
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((72, 100), u"第二页 SECOND PAGE", fontsize=20, fontname="china-s")
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return path


def main():
    sample = make_sample(os.path.join(SAMPLE_DIR, "sample.pdf"))
    print("样例文件:", sample)

    doc = PdfDocument()

    def t_open():
        doc.open(sample)
        assert doc.page_count == 2, doc.page_count
        assert doc.title

    check("打开文档", t_open)

    def t_render():
        samples, w, h, stride, zoom = doc.render(0, 1.5)
        assert w > 100 and h > 100
        assert len(samples) == stride * h, (len(samples), stride, h)

    check("页面渲染", t_render)

    def t_text():
        text = doc.page_text(0)
        assert u"统信" in norm(text), text[:200]
        spans = doc.page_spans(0)
        assert len(spans) >= 3
        hit = doc.span_at(0, (spans[0]["bbox"][0] + 2, spans[0]["bbox"][1] + 4))
        assert hit is not None

    check("文本提取 / 命中", t_text)

    def t_search():
        hits = doc.search(u"统信")
        assert len(hits) >= 18, len(hits)
        assert hits[0][0] == 0
        # 容错搜索：文字层被拆成"统 信 U O S"时也应命中
        fuzzy = doc.search(u"统信UOS")
        assert len(fuzzy) >= 18, len(fuzzy)

    check("全文搜索", t_search)

    def t_highlight():
        doc.begin_change(u"高亮")
        page = doc.doc[0]
        annot = annotate.add_markup(page, "highlight", fitz.Rect(70, 78, 400, 96),
                                    (1.0, 0.86, 0.24), 0.6)
        doc.end_change()
        assert annot is not None
        items = annotate.list_annotations(doc, 0)
        assert len(items) == 1, items

    check("添加高亮注释", t_highlight)

    def t_annot_ops():
        items = annotate.list_annotations(doc, 0)
        xref = items[0]["xref"]
        ok = annotate.update_annotation(doc, 0, xref, color=(0.3, 0.7, 1.0), opacity=0.4)
        assert ok
        found = annotate.annotation_at(doc, 0, (100, 86))
        assert found is not None
        assert annotate.delete_annotation(doc, 0, xref)
        assert not annotate.list_annotations(doc, 0)

    check("注释更新 / 命中 / 删除", t_annot_ops)

    def t_ink_and_shape():
        doc.begin_change(u"绘制")
        page = doc.doc[0]
        annotate.add_ink(page, [[(100, 400), (150, 430), (200, 405)]], (0.9, 0.2, 0.2), 2.5)
        annotate.add_shape(page, "rect", fitz.Rect(300, 400, 460, 470), (0.1, 0.4, 0.9), 2.0)
        annotate.add_shape(page, "ellipse", fitz.Rect(300, 500, 460, 560), (0.1, 0.7, 0.4), 2.0)
        annotate.add_arrow(page, (100, 520), (250, 560), (0.2, 0.2, 0.2), 2.0)
        annotate.add_textbox(page, fitz.Rect(100, 600, 400, 660), u"文本框注释：已审核", 14, (0, 0, 0))
        annotate.add_note(page, (500, 200), u"这里有一个便签")
        doc.end_change()
        items = annotate.list_annotations(doc, 0)
        types = [i["type_cn"] for i in items]
        # 文本框现在是页面内容而不是注释，所以这里只统计注释类对象
        assert len(items) >= 5, types
        assert u"文本框注释" in norm(doc.page_text(0)), "文本框内容没有写入页面"

    check("手绘 / 图形 / 文本框 / 便签", t_ink_and_shape)

    def t_replace_text():
        doc.begin_change(u"改字")
        page = doc.doc[0]
        span = None
        for s in doc.page_spans(0):
            if u"示例文字" in s["text"]:
                span = s
                break
        assert span is not None
        textops.replace_span_text(page, span, u"这是替换后的全新内容。")
        doc.end_change()
        text = doc.page_text(0)
        assert u"替换后的全新内容" in text, text[:300]
        assert u"示例文字" not in text

    check("替换页面文字", t_replace_text)

    def t_insert_text():
        doc.begin_change(u"加字")
        textops.insert_text(doc.doc[0], (72, 780), u"插入的新段落", 14, (0.8, 0.1, 0.1))
        doc.end_change()
        assert u"插入的新段落" in doc.page_text(0)

    check("插入新文字", t_insert_text)

    def t_watermark():
        doc.begin_change(u"水印")
        n = decorate.add_watermark(doc, u"内部资料", font_size=60, opacity=0.18, angle=45)
        doc.end_change()
        assert n == 2

    check("添加水印", t_watermark)

    def t_page_numbers():
        doc.begin_change(u"页码")
        n = decorate.add_page_numbers(doc, template=u"第 {page} 页 / 共 {total} 页")
        doc.end_change()
        assert n == 2
        assert u"第1页" in norm(doc.page_text(0))

    check("添加页码", t_page_numbers)

    def t_undo_redo():
        before = doc.page_count
        doc.begin_change(u"插入空白页")
        pageops.insert_blank_page(doc, 1)
        doc.end_change()
        assert doc.page_count == before + 1
        assert doc.can_undo()
        doc.undo()
        assert doc.page_count == before, doc.page_count
        doc.redo()
        assert doc.page_count == before + 1
        doc.undo()

    check("撤销 / 重做", t_undo_redo)

    def t_rotate():
        doc.begin_change(u"旋转")
        pageops.rotate_pages(doc, [0], 90)
        doc.end_change()
        assert doc.doc[0].rotation == 90
        doc.undo()

    check("旋转页面", t_rotate)

    def t_move():
        doc.begin_change(u"移动")
        pageops.move_page(doc, 0, 1)
        doc.end_change()
        assert u"第二页" in norm(doc.page_text(0))
        doc.undo()
        assert u"PDFStudio" in norm(doc.page_text(0))

    check("调整页序", t_move)

    def t_insert_from_file():
        before = doc.page_count
        doc.begin_change(u"插入文件")
        pageops.insert_from_file(doc, sample, 1)
        doc.end_change()
        assert doc.page_count == before + 2
        doc.undo()
        assert doc.page_count == before

    check("插入外部页面", t_insert_from_file)

    def t_extract():
        out = os.path.join(OUT, "extracted.pdf")
        pageops.extract_pages(doc, [1], out)
        assert os.path.isfile(out) and os.path.getsize(out) > 500

    check("提取页面", t_extract)

    def t_split():
        out_dir = os.path.join(OUT, "split")
        files = pageops.split_each_page(doc, out_dir)
        assert len(files) == doc.page_count, files

    check("拆分文档", t_split)

    def t_merge():
        out = os.path.join(OUT, "merged.pdf")
        pageops.merge_files([sample, sample], out)
        merged = fitz.open(out)
        assert merged.page_count == 4
        merged.close()

    check("合并文档", t_merge)

    def t_outline():
        doc.begin_change(u"目录")
        doc.set_outline([[1, u"第一页", 1], [1, u"第二页", 2]])
        doc.end_change()
        toc = doc.outline()
        assert len(toc) == 2
        doc.undo()

    check("写入书签目录", t_outline)

    def t_compress():
        out = os.path.join(OUT, "compressed.pdf")
        export.compress_to(doc, out, level="standard")
        assert os.path.isfile(out)
        out2 = os.path.join(OUT, "compressed_strong.pdf")
        export.compress_to(doc, out2, level="strong", dpi=110, quality=70)
        assert os.path.getsize(out2) > 1000

    check("压缩（标准 / 强力）", t_compress)

    def t_encrypt():
        out = os.path.join(OUT, "locked.pdf")
        security.encrypt_to(doc, out, u"123456", u"admin")
        locked = fitz.open(out)
        assert locked.needs_pass
        assert locked.authenticate(u"123456")
        locked.close()
        sub = PdfDocument()
        try:
            sub.open(out, u"wrong")
            raise AssertionError("错误密码应当失败")
        except PdfError as exc:
            assert exc.code == "password"
        sub.open(out, u"123456")
        assert sub.page_count == doc.page_count
        dec = os.path.join(OUT, "unlocked.pdf")
        security.decrypt_to(sub, dec)
        check_doc = fitz.open(dec)
        assert not check_doc.needs_pass
        check_doc.close()
        sub.close()

    check("加密 / 解密", t_encrypt)

    def t_redact():
        doc.begin_change(u"涂黑")
        n = security.redact_text(doc, u"第 3 行内容")
        doc.end_change()
        assert n >= 1
        assert u"第 3 行内容" not in doc.page_text(0)

    check("涂黑脱敏", t_redact)

    def t_export():
        out_dir = os.path.join(OUT, "images")
        files = doc.export_images(out_dir, pages=[0], dpi=100)
        assert len(files) == 1 and os.path.getsize(files[0]) > 1000
        txt = os.path.join(OUT, "text.txt")
        doc.export_text(txt)
        assert os.path.getsize(txt) > 100
        long_img = os.path.join(OUT, "long.png")
        export.to_long_image(doc, long_img, dpi=70)
        assert os.path.getsize(long_img) > 5000

    check("导出图片 / 文本 / 长图", t_export)

    def t_save():
        out = os.path.join(OUT, "saved.pdf")
        doc.save(out)
        assert os.path.isfile(out)
        reopened = PdfDocument()
        reopened.open(out)
        assert reopened.page_count == doc.page_count
        reopened.close()
        # 覆盖保存（同路径原子替换）
        doc.save()
        assert doc.page_count >= 1

    check("保存 / 覆盖保存", t_save)

    def t_save_locked():
        """目标文件被别的程序占用时，覆盖保存要给出看得懂的提示。

        Windows 上文件被打开着（另一个阅读器、网盘同步、杀软扫描）时
        原子替换会失败。这里模拟"占用"，确认不会崩、提示是中文、
        而且放开占用之后还能正常保存。
        """
        out = os.path.join(OUT, "locked.pdf")
        doc.save(out)
        holder = open(out, "rb")
        try:
            try:
                doc.save()
            except PdfError as exc:
                assert exc.code == "locked", exc.code
                assert u"打开" in str(exc), str(exc)
            else:
                # POSIX 上替换不受占用影响，走到这里也算正常
                assert os.name != "nt", "Windows 上应当报占用错误"
        finally:
            holder.close()
        # 放开占用后必须能正常保存
        doc.save()
        assert os.path.getsize(out) > 1000

    check("文件被占用时的覆盖保存", t_save_locked)

    def t_metadata():
        doc.begin_change(u"元数据")
        doc.set_metadata({"title": u"测试标题", "author": u"测试作者"})
        doc.end_change()
        meta = doc.metadata()
        assert meta.get("title") == u"测试标题"
        assert doc.title == u"测试标题"

    check("元数据读写", t_metadata)

    def t_ocr_guard():
        try:
            textops.ocr_page_text(doc.doc[0])
        except PdfError as exc:
            assert exc.code == "ocr"

    check("OCR 缺失时给出友好提示", t_ocr_guard)

    # ---------------- 多文档合并 ----------------
    def make_tags_pdf(path, count, tag):
        """每页只写一行 "TAG-n"，这样能按文字反查输出页序。"""
        d = fitz.open()
        for i in range(count):
            page = d.new_page(width=595, height=842)
            page.insert_text((72, 100), "%s-%d" % (tag, i + 1),
                             fontsize=28, fontname="helv")
        d.save(path, garbage=3, deflate=True)
        d.close()
        return path

    def tags_of(path):
        d = fitz.open(path)
        try:
            return [p.get_text("text").strip() for p in d]
        finally:
            d.close()

    merge_a = make_tags_pdf(os.path.join(OUT, "merge_a.pdf"), 3, "A")
    merge_b = make_tags_pdf(os.path.join(OUT, "merge_b.pdf"), 2, "B")
    merged = os.path.join(OUT, "merged.pdf")

    def t_merge_basic():
        plan = merge_mod.MergePlan()
        try:
            plan.add_source(merge_a)
            plan.add_source(merge_b)
            assert plan.file_count == 2, plan.file_count
            assert plan.total_pages == 5, plan.total_pages
            plan.build(merged)
        finally:
            plan.close()
        assert tags_of(merged) == ["A-1", "A-2", "A-3", "B-1", "B-2"], tags_of(merged)

    check("合并两个文件（默认顺序）", t_merge_basic)

    def t_merge_custom_order():
        plan = merge_mod.MergePlan()
        try:
            ia = plan.add_source(merge_a)
            ib = plan.add_source(merge_b)
            # 模拟拖拽后的乱序：B2, A3, A1, B1, A2
            plan.set_order([(ib, 1), (ia, 2), (ia, 0), (ib, 0), (ia, 1)])
            plan.build(merged)
        finally:
            plan.close()
        assert tags_of(merged) == ["B-2", "A-3", "A-1", "B-1", "A-2"], tags_of(merged)

    check("按自定义页序合并（拖拽排序）", t_merge_custom_order)

    def t_merge_runs():
        """连续页要压成区间，但压完结果不能变。"""
        plan = merge_mod.MergePlan()
        try:
            ia = plan.add_source(merge_a)
            ib = plan.add_source(merge_b)
            order = [(ia, 0), (ia, 1), (ia, 2), (ib, 0), (ib, 1)]
            runs = merge_mod._runs(order)
            assert runs == [(ia, 0, 2), (ib, 0, 1)], runs
            # 交错的情况不能被错误合并
            mixed = [(ia, 0), (ib, 0), (ia, 1)]
            assert merge_mod._runs(mixed) == [(ia, 0, 0), (ib, 0, 0), (ia, 1, 1)]
        finally:
            plan.close()

    check("连续页压成区间且不改变结果", t_merge_runs)

    def t_merge_drop_pages():
        plan = merge_mod.MergePlan()
        try:
            plan.add_source(merge_a)
            plan.add_source(merge_b)
            removed = plan.drop_pages([0, 2, 4])  # A-1, A-3, B-2
            assert removed == 3, removed
            assert plan.total_pages == 2, plan.total_pages
            plan.build(merged)
        finally:
            plan.close()
        assert tags_of(merged) == ["A-2", "B-1"], tags_of(merged)

    check("删除部分页面后合并", t_merge_drop_pages)

    def t_merge_remove_source():
        """移除文件后，后面文件的下标要整体前移，否则会指向错的文件。"""
        plan = merge_mod.MergePlan()
        try:
            plan.add_source(merge_a)
            ib = plan.add_source(merge_b)
            assert ib == 1, ib
            plan.remove_source(0)
            assert plan.file_count == 1, plan.file_count
            assert plan.order == [(0, 0), (0, 1)], plan.order
            assert plan.kept_pages(0) == 2
            plan.build(merged)
        finally:
            plan.close()
        assert tags_of(merged) == ["B-1", "B-2"], tags_of(merged)

    check("移除源文件后下标正确前移", t_merge_remove_source)

    def t_merge_password():
        locked = os.path.join(OUT, "merge_locked.pdf")
        d = fitz.open()
        page = d.new_page()
        page.insert_text((72, 100), "LOCKED", fontsize=28, fontname="helv")
        d.save(locked, encryption=fitz.PDF_ENCRYPT_AES_256,
               owner_pw="admin", user_pw="123456")
        d.close()

        plan = merge_mod.MergePlan()
        try:
            try:
                plan.add_source(locked)
                raise AssertionError("加密文件不该在无密码时加入")
            except PdfError as exc:
                assert exc.code == "password", exc.code
            assert plan.file_count == 0, "失败的文件不能留在计划里"
            index = plan.add_source(locked, "123456")
            assert index == 0
            assert plan.total_pages == 1
            plan.build(merged)
        finally:
            plan.close()
        assert tags_of(merged) == ["LOCKED"], tags_of(merged)

    check("加密文件需要密码", t_merge_password)

    def t_merge_bad_source():
        broken = os.path.join(OUT, "merge_broken.pdf")
        with open(broken, "wb") as fh:
            fh.write(b"this is not a pdf at all")
        plan = merge_mod.MergePlan()
        try:
            try:
                plan.add_source(broken)
                raise AssertionError("损坏文件不该加入成功")
            except PdfError as exc:
                assert exc.code == "parse", exc.code
            assert plan.file_count == 0, "失败的文件不能留在计划里"
            assert plan.total_pages == 0
        finally:
            plan.close()

    check("损坏文件给出明确错误", t_merge_bad_source)

    def t_merge_empty():
        plan = merge_mod.MergePlan()
        try:
            plan.build(merged)
            raise AssertionError("空计划不该写出文件")
        except PdfError as exc:
            assert exc.code == "empty", exc.code
        finally:
            plan.close()

    check("没有页面时拒绝合并", t_merge_empty)

    def t_merge_order_guard():
        plan = merge_mod.MergePlan()
        try:
            plan.add_source(merge_b)
            try:
                plan.set_order([(0, 0)])  # 少了一页
                raise AssertionError("页序不完整应当报错")
            except PdfError as exc:
                assert exc.code == "order", exc.code
            try:
                plan.set_order([(0, 0), (0, 0)])  # 重复
                raise AssertionError("页序重复应当报错")
            except PdfError as exc:
                assert exc.code == "order", exc.code
        finally:
            plan.close()

    check("页序不完整 / 重复时报错", t_merge_order_guard)

    def t_merge_overwrite():
        """覆盖同名文件要真的覆盖掉，不能留半截旧内容。"""
        with open(merged, "wb") as fh:
            fh.write(b"old junk" * 2000)
        plan = merge_mod.MergePlan()
        try:
            plan.add_source(merge_b)
            plan.build(merged)
        finally:
            plan.close()
        assert tags_of(merged) == ["B-1", "B-2"], tags_of(merged)

    check("覆盖已存在的输出文件", t_merge_overwrite)

    def t_merge_natural_sort():
        paths = [os.path.join(OUT, "第10章.pdf"),
                 os.path.join(OUT, "第2章.pdf"),
                 os.path.join(OUT, "第1章.pdf")]
        got = [os.path.basename(p) for p in merge_mod.sort_paths(paths)]
        assert got == ["第1章.pdf", "第2章.pdf", "第10章.pdf"], got
        # 同一个文件重复选中只留一份
        assert len(merge_mod.sort_paths([paths[0], paths[0]])) == 1

    check("文件名按自然顺序排列", t_merge_natural_sort)

    def t_release_collect():
        """发行包收集规则：该在的都在，构建残留一个都不许进。

        这条守的是"包比源码旧"这类事故：源码目录里测试全绿，交付出去
        的包却是上周打的，连整个合并功能都不在里面。打包脚本在 Windows
        上没有 bash 跑不起来，正是没人重打的原因。
        """
        import importlib.util

        path = os.path.join(ROOT, "packaging", "make_release.py")
        spec = importlib.util.spec_from_file_location("_make_release", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        got = {rel for rel, _full in mod.collect(False)}

        # 交付的包必须能真正跑起来：入口、所有 core/ui 模块、安装脚本
        must = mod.REQUIRED + ["tests/smoke_core.py", "packaging/make_release.py"]
        missing = [rel for rel in must if rel not in got]
        assert not missing, "发行包会缺文件：%r" % (missing,)

        # PyInstaller 的 dist8 / build8 是 Windows 构建产物，进了包体积会翻
        # 十几倍，而且没人会去 UOS 上解压一堆 exe
        leaked = [rel for rel in got if rel.startswith("packaging/windows/dist")
                  or rel.startswith("packaging/windows/build")]
        assert not leaked, "构建残留混进发行包：%r" % (leaked[:5],)

        bad = [rel for rel in got if "__pycache__" in rel or rel.endswith(".pyc")
               or "/_out/" in rel or "/_test/" in rel]
        assert not bad, "测试/缓存产物混进发行包：%r" % (bad[:5],)

        # wheel 是 80MB，纯源码包必须不含；带 --with-wheels 时必须真带上，
        # 否则 UOS 上装不上依赖（apt 源封闭）
        assert not any(rel.startswith("packaging/wheels/") for rel in got), \
            "没加 --with-wheels 却打进了 wheel"
        if os.path.isdir(os.path.join(ROOT, "packaging", "wheels")):
            whls = [rel for rel, _full in mod.collect(True) if rel.endswith(".whl")]
            assert len(whls) >= 4, "有 wheels 目录却只收到 %d 个" % len(whls)

    check("发行包收集规则（不缺文件、不带构建残留）", t_release_collect)

    print("\n通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失败项：", [f[0] for f in FAIL])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
