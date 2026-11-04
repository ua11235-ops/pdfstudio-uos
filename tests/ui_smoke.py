# -*- coding: utf-8 -*-
"""界面层自测：在 offscreen 平台下真实构建窗口并截图，验证不会崩溃、布局正常。"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# 同目录的 _thumb_probe 也要能 import 到（脚本方式运行时其实已经在了）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 用真实平台渲染（离屏平台没有字体库，截图里中文会变成方框），
# 但通过 WA_DontShowOnScreen 让窗口完成排版却不真正弹到桌面上。
os.environ.pop("QT_QPA_PLATFORM", None)

from pdfstudio.qtcompat import QtCore, QtGui, QtWidgets, Qt, qexec  # noqa: E402
from pdfstudio.ui import theme, icons  # noqa: E402
from pdfstudio.ui.main_window import MainWindow  # noqa: E402
from pdfstudio.ui import dialogs  # noqa: E402

# 测试截图单独放一个目录，避免污染文档用的成品截图
OUT = os.path.join(ROOT, "screenshots", "_test")
os.makedirs(OUT, exist_ok=True)

SAMPLE = os.path.join(ROOT, "samples", "sample.pdf")

PASS = []
FAIL = []


def check(name, fn):
    try:
        fn()
        PASS.append(name)
        print("  [ok] %s" % name)
    except Exception as exc:
        import traceback
        FAIL.append((name, exc))
        print("  [FAIL] %s -> %r" % (name, exc))
        traceback.print_exc()


def hide_offscreen(widget):
    widget.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
    return widget


def pump(app, ms=120):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def main():
    app = QtWidgets.QApplication(sys.argv)
    theme.apply(app)
    win = hide_offscreen(MainWindow())
    win.resize(1400, 900)
    win.show()
    pump(app, 200)

    def t_initial():
        assert win.windowTitle()
        assert not win.actions["save"].isEnabled()

    check("空窗口初始化", t_initial)

    win.grab().save(os.path.join(OUT, "01_empty.png"))

    def t_open():
        win.open_path(SAMPLE)
        pump(app, 1200)
        assert win.doc.is_open
        assert win.doc.page_count == 2
        assert win.page_view.zoom > 0.1
        assert win.actions["save"].isEnabled()

    check("打开文档并自适应宽度", t_open)

    def t_nav():
        win.goto_page(1)
        pump(app, 150)
        assert win.page_view.page_index == 1
        assert win.page_spin.value() == 2
        win.goto_page(0)
        pump(app, 150)
        assert win.page_view.page_index == 0

    check("翻页与页码联动", t_nav)

    def t_zoom():
        win.page_view.set_zoom(1.0)
        pump(app, 150)
        assert abs(win.page_view.zoom - 1.0) < 0.01
        win.zoom_by(1.2)
        pump(app, 100)
        assert win.page_view.zoom > 1.0
        win.fit_page()
        pump(app, 100)

    check("缩放", t_zoom)

    def t_tools():
        for key, _label, _icon, _hint in __import__(
                "pdfstudio.ui.page_view", fromlist=["TOOLS"]).TOOLS:
            win._set_tool(key)
            pump(app, 10)
        win._set_tool("highlight")
        assert win.page_view.tool == "highlight"

    check("切换全部工具", t_tools)

    def t_find():
        win.find_bar.focus_edit()
        win.run_search(u"统信")
        pump(app, 250)
        assert len(win._find_hits) >= 18, len(win._find_hits)
        win.step_search(1)
        pump(app, 150)
        assert win.page_view._search_hits

    check("查找并高亮", t_find)

    def t_annotate_programmatic():
        # 通过核心 API 加注释，验证视图能重新渲染
        win._set_tool("highlight")
        win.doc.begin_change(u"测试高亮")
        from pdfstudio.core import annotate as ann
        import pymupdf as fitz
        ann.add_markup(win.doc.doc[0], "highlight", fitz.Rect(70, 118, 420, 140),
                       (1.0, 0.86, 0.24), 0.5)
        win.doc.end_change()
        pump(app, 250)
        items = ann.list_annotations(win.doc)
        assert items, "注释列表为空"

    check("注释写入后视图刷新", t_annotate_programmatic)

    def t_panels():
        win.side.setCurrentIndex(1)
        pump(app, 100)
        win.side.setCurrentIndex(2)
        pump(app, 100)
        win.side.setCurrentIndex(0)
        pump(app, 300)

    check("侧栏三个页签", t_panels)

    win.find_bar.hide()
    win.page_view.set_zoom(1.0)
    win.goto_page(0)
    pump(app, 1200)
    win.grab().save(os.path.join(OUT, "02_main.png"))

    def t_undo_redo():
        before = win.doc.page_count
        win.insert_blank_page()
        pump(app, 200)
        assert win.doc.page_count == before + 1
        win.undo()
        pump(app, 200)
        assert win.doc.page_count == before
        win.redo()
        pump(app, 200)
        assert win.doc.page_count == before + 1
        win.undo()
        pump(app, 200)

    check("插入页面 + 撤销重做", t_undo_redo)

    def t_page_ops():
        n = win.doc.page_count
        win.insert_blank_after(0)
        pump(app, 500)      # 侧栏刷新有 350ms 防抖，等够再查
        assert win.doc.page_count == n + 1, win.doc.page_count

        # 插入页之后缩略图必须保持正常尺寸。新增条目如果没有图标，
        # 在 uniformItemSizes 下会把整列缩成一条，用户就点不中了。
        # 注意要测「可见条目的实际矩形」，只查 icon 是否为空抓不住这个 bug
        # —— 异步渲染很快会把图标补上，但布局已经被压扁了。
        thumbs = win.side.thumbs
        rect = thumbs.visualItemRect(thumbs.item(0))
        assert rect.height() >= 100, ("缩略图被压扁", rect.width(), rect.height())

        win.rotate_pages([0, 1], 90)
        pump(app, 150)
        assert win.doc.doc[0].rotation == 90
        assert win.doc.doc[1].rotation == 90

        win.move_page_to(0, win.doc.page_count - 1)
        pump(app, 150)

        win.delete_pages([0])
        pump(app, 150)
        assert win.doc.page_count == n, win.doc.page_count

        for _ in range(4):
            win.undo()
        pump(app, 250)
        assert win.doc.page_count == n
        assert win.doc.doc[0].rotation == 0, win.doc.doc[0].rotation

    check("批量页面操作（插入/旋转/移动/删除/撤销）", t_page_ops)

    def t_watermark():
        from pdfstudio.core import decorate
        win.doc.begin_change(u"水印")
        decorate.add_watermark(win.doc, u"内部资料", font_size=54, opacity=0.18, angle=45)
        win.doc.end_change()
        pump(app, 300)
        assert u"内部资料" in win.doc.page_text(0)

    check("水印后重新渲染", t_watermark)

    win.grab().save(os.path.join(OUT, "03_watermark.png"))

    def t_dialogs():
        made = [
            dialogs.WatermarkDialog(win),
            dialogs.PageNumberDialog(win),
            dialogs.EncryptDialog(win),
            dialogs.CompressDialog(win, 1024 * 1024 * 3),
            dialogs.ExportImageDialog(win),
            dialogs.SplitDialog(win, 12),
            dialogs.MetadataDialog(win.doc.metadata(), win),
            dialogs.RedactTextDialog(win),
            dialogs.TextInputDialog(u"修改文字", u"编辑内容", u"原文", win),
            dialogs.AboutDialog(win, "PySide6", "1.24.14"),
        ]
        for dialog in made:
            hide_offscreen(dialog)
            dialog.show()
            pump(app, 40)
            dialog.grab().save(os.path.join(OUT, "dlg_%s.png" % dialog.windowTitle()[:8]))
            dialog.close()
        assert len(made) == 10

    check("全部对话框可构建", t_dialogs)

    def t_icons():
        names = ["open", "save", "undo", "redo", "zoom_in", "zoom_out", "fit_width",
                 "hand", "cursor", "highlight", "ink", "note", "watermark", "lock",
                 "redact", "form", "pages", "arrow", "eraser", "search"]
        for name in names:
            pm = icons.pixmap(name, 24)
            assert not pm.isNull()
        icons.app_icon(256).save(os.path.join(OUT, "app_icon.png"))

    check("图标绘制", t_icons)

    def t_thumbs_sync():
        """页面增删之后，缩略图必须和文档完全对上。

        用户反馈过"插入/删除页面之后缩略图有问题"，出问题的点不止一处：
        条目数、条目文字、格子尺寸、画的内容，四样都得查，
        只查其中一样就会漏掉其余几样。

        这里换一份每页颜色都不同的文档——sample.pdf 每页都是白底黑字，
        粗粒度指纹分不出来，"画成别的页"这种错就抓不住。
        """
        import tempfile
        from _thumb_probe import (settle as settle_thumbs, mismatch,
                                  make_color_pdf, TOLERANCE)
        path = make_color_pdf(
            os.path.join(tempfile.gettempdir(), "ui_smoke_thumbs.pdf"), 10)
        win.doc.dirty = False       # 前面用例改过文档，别弹保存询问
        win.open_path(path)
        settle_thumbs(app, win)

        thumbs = win.side.thumbs

        def verify(tag):
            assert thumbs.count() == win.doc.page_count, (
                tag, thumbs.count(), win.doc.page_count)
            for i in range(thumbs.count()):
                item = thumbs.item(i)
                assert item is not None, (tag, i)
                assert item.text() == "第 %d 页" % (i + 1), (tag, i, item.text())
                assert item.data(QtCore.Qt.UserRole) == i, (tag, i)
                worst = mismatch(win.doc, item, i)
                assert worst is None or worst <= TOLERANCE, (
                    tag + " 缩略图画错页", i, worst)
            rect = thumbs.visualItemRect(thumbs.item(0))
            assert rect.height() >= 100, (tag + " 缩略图被压扁",
                                          rect.width(), rect.height())

        verify("初始")

        win.insert_blank_after(0)
        # 操作刚结束、图还没画完时就量尺寸：这一步专抓"格子被压扁"。
        # 等图都画完了 Qt 会自己重排，那时候再量什么都查不出来。
        pump(app, 460)
        assert thumbs.count() == win.doc.page_count
        rect = thumbs.visualItemRect(thumbs.item(0))
        assert rect.height() >= 100, ("插入后缩略图被压扁",
                                      rect.width(), rect.height())
        settle_thumbs(app, win)
        verify("插入后")

        win.delete_pages([0])
        settle_thumbs(app, win)
        verify("删首页后")

        win.delete_pages([win.doc.page_count // 2])
        settle_thumbs(app, win)
        verify("删中间页后")

        win.delete_pages([win.doc.page_count - 1])
        settle_thumbs(app, win)
        verify("删末页后")

        win.move_page_to(0, win.doc.page_count - 1)
        settle_thumbs(app, win)
        verify("换序后")

        for _ in range(10):
            if not win.doc.can_undo():
                break
            win.undo()
        settle_thumbs(app, win)
        verify("撤销后")

    check("增删页面后缩略图与文档一致", t_thumbs_sync)

    def t_thumbs_mixed_size():
        """页面尺寸混杂时，缩略图格子不能被页面比例带跑。

        公文里常混着长条页、横向表格页。只按宽度算缩放的话，
        长条页会算出比格子高的图标，被格子裁掉上下、间距也跟着乱。
        """
        import tempfile
        from _thumb_probe import (settle as settle_thumbs, mismatch,
                                  make_mixed_pdf, THUMB_WIDTH, THUMB_HEIGHT,
                                  TOLERANCE)
        path = make_mixed_pdf(
            os.path.join(tempfile.gettempdir(), "ui_smoke_mixed.pdf"))
        win.doc.dirty = False
        win.open_path(path)
        settle_thumbs(app, win)

        thumbs = win.side.thumbs
        assert thumbs.count() == win.doc.page_count

        sizes = set()
        rects = set()
        for i in range(thumbs.count()):
            item = thumbs.item(i)
            pm = item.icon().pixmap(THUMB_WIDTH, THUMB_HEIGHT)
            sizes.add((pm.width(), pm.height()))
            r = thumbs.visualItemRect(item)
            if r.height() > 0:
                rects.add((r.width(), r.height()))
            worst = mismatch(win.doc, item, i)
            assert worst is None or worst <= TOLERANCE, ("缩略图画错页", i, worst)

        assert sizes == {(THUMB_WIDTH, THUMB_HEIGHT)}, ("图标尺寸不统一", sizes)
        assert len(rects) == 1, ("格子尺寸不统一", rects)

        # 删页之后同样要保持一致
        win.delete_pages([2])
        settle_thumbs(app, win)
        sizes = set()
        for i in range(thumbs.count()):
            pm = thumbs.item(i).icon().pixmap(THUMB_WIDTH, THUMB_HEIGHT)
            sizes.add((pm.width(), pm.height()))
        assert sizes == {(THUMB_WIDTH, THUMB_HEIGHT)}, ("删页后图标尺寸不统一", sizes)

    check("页面尺寸混杂时格子保持一致", t_thumbs_mixed_size)

    def t_thumbs_drag_reorder():
        """缩略图拖拽：真实鼠标按下 -> 移动 -> 松手，文档页序必须真的变。

        和合并窗口同一个道理——不用 Qt 内置拖拽（QDrag::exec 是模态循环，
        进不去也测不到），所以这里可以用 QTest 把整条鼠标链路走完。

        断言看的是**文档里每页的实际内容**，不是界面上的文字标签：
        标签可以重编号得很正确，而底层页面根本没换，那种假绿必须排除。
        """
        import tempfile
        import pymupdf as fitz
        from PySide6.QtTest import QTest
        from _thumb_probe import settle as settle_thumbs

        path = os.path.join(tempfile.gettempdir(), "ui_smoke_reorder.pdf")
        src = fitz.open()
        for i in range(8):
            page = src.new_page(width=595, height=842)
            page.insert_text((72, 100), "P-%d" % (i + 1), fontsize=30, fontname="helv")
        src.save(path, garbage=3, deflate=True)
        src.close()

        win.doc.dirty = False
        win.open_path(path)
        settle_thumbs(app, win)

        def tags():
            out = []
            for i in range(win.doc.page_count):
                text = win.doc.doc[i].get_text("text").strip().splitlines()
                out.append(text[0].strip() if text else "")
            return out

        thumbs = win.side.thumbs
        assert thumbs.count() == 8, thumbs.count()

        def drag(src_row, dst_row, half="back"):
            rect = thumbs.visualItemRect(thumbs.item(dst_row))
            press = thumbs.visualItemRect(thumbs.item(src_row)).center()
            if half == "back":
                target = QtCore.QPoint(rect.right() - 6, rect.center().y())
            else:
                target = QtCore.QPoint(rect.left() + 6, rect.center().y())
            QTest.mousePress(thumbs.viewport(), Qt.LeftButton,
                             Qt.KeyboardModifier.NoModifier, press)
            pump(app, 30)
            steps = 6
            for step in range(1, steps + 1):
                pos = QtCore.QPoint(
                    press.x() + (target.x() - press.x()) * step // steps,
                    press.y() + (target.y() - press.y()) * step // steps)
                QTest.mouseMove(thumbs.viewport(), pos)
                pump(app, 20)
            QTest.mouseRelease(thumbs.viewport(), Qt.LeftButton,
                               Qt.KeyboardModifier.NoModifier, target)
            pump(app, 200)

        # 1) 第 1 页拖到第 4 页后面
        drag(0, 3)
        assert tags() == ["P-2", "P-3", "P-4", "P-1", "P-5", "P-6", "P-7", "P-8"], tags()

        # 2) 最后一页拖到最前面
        drag(7, 0, half="front")
        assert tags() == ["P-8", "P-2", "P-3", "P-4", "P-1", "P-5", "P-6", "P-7"], tags()

        # 3) 拖拽要能撤销（和右键菜单里的"上移/下移"走同一条路）
        assert win.doc.can_undo(), "拖拽后必须能撤销"
        win.undo()
        settle_thumbs(app, win)
        assert tags() == ["P-2", "P-3", "P-4", "P-1", "P-5", "P-6", "P-7", "P-8"], \
            ("撤销没退回原顺序", tags())

        # 4) 缩略图重编号必须跟着新页序走，否则点第 N 张会跳到别的页
        assert thumbs.item(0).text() == "第 1 页", thumbs.item(0).text()
        assert thumbs.item(0).data(Qt.UserRole) == 0, thumbs.item(0).data(Qt.UserRole)

        # 5) 只是点一下（没超过拖拽阈值）不能改页序
        before = tags()
        centre = thumbs.visualItemRect(thumbs.item(2)).center()
        QTest.mousePress(thumbs.viewport(), Qt.LeftButton,
                         Qt.KeyboardModifier.NoModifier, centre)
        QTest.mouseRelease(thumbs.viewport(), Qt.LeftButton,
                           Qt.KeyboardModifier.NoModifier, centre)
        pump(app, 50)
        assert tags() == before, "单击不该改变页序"

        # 6) 拖回原地：顺序不变，也不能留下拖拽残留状态
        drag(1, 1, half="front")
        assert tags() == before, "拖回原地不该改变页序"
        assert thumbs._drag_start is None and not thumbs._dragging
        assert thumbs._drop_row is None, "落点标记要在松手后清掉"

    check("缩略图拖拽能直接改页序", t_thumbs_drag_reorder)

    def t_thumbs_gesture_split():
        """缩略图上"拖页排序"和"框选"必须是两种互斥的手势。

        用户报的症状是"拖动事件和框选事件重复了"：按住空白处拖动时，
        框在画、页面顺序也在动。根因是 mouseMoveEvent 在越过拖拽阈值之前
        把事件统一转给了基类，基类于是开始橡皮筋框选，而我们同时也在算落点。

        现在按"按下位置"把手势分开，并逐帧断言：
          - 按在条目上拖：只出现落点线，全程不出现框选矩形
          - 按在空白处拖：只出现框选矩形，页序一页都不能动
        """
        import tempfile
        import pymupdf as fitz
        from PySide6.QtTest import QTest
        from _thumb_probe import settle as settle_thumbs

        path = os.path.join(tempfile.gettempdir(), "ui_smoke_gesture.pdf")
        src = fitz.open()
        for i in range(10):
            page = src.new_page(width=595, height=842)
            page.insert_text((72, 100), "P-%d" % (i + 1), fontsize=30, fontname="helv")
        src.save(path, garbage=3, deflate=True)
        src.close()

        win.doc.dirty = False
        win.open_path(path)
        settle_thumbs(app, win)

        thumbs = win.side.thumbs
        vp = thumbs.viewport()

        def tags():
            out = []
            for i in range(win.doc.page_count):
                text = win.doc.doc[i].get_text("text").strip().splitlines()
                out.append(text[0].strip() if text else "")
            return out

        # ---- 1) 按在条目上拖动：只排序，不框选 ----
        thumbs.clearSelection()
        thumbs.setCurrentRow(0)
        pump(app, 20)
        before = tags()
        press = thumbs.visualItemRect(thumbs.item(0)).center()
        QTest.mousePress(vp, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, press)
        pump(app, 20)
        band_ever_shown = False
        pos = press
        for step in range(1, 9):
            pos = QtCore.QPoint(press.x(), press.y() + step * 40)
            QTest.mouseMove(vp, pos)
            pump(app, 20)
            if thumbs._band_rect is not None:
                band_ever_shown = True
        assert not band_ever_shown, "拖整页时不该出现框选矩形"
        assert thumbs._drag_mode == thumbs._DRAG_PAGE, thumbs._drag_mode
        QTest.mouseRelease(vp, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, pos)
        pump(app, 300)
        assert tags() != before, "按在条目上拖动应该改变页序"

        # ---- 2) 按在空白处拖动：只框选，页序不许动 ----
        settle_thumbs(app, win)
        vp_rect = vp.rect()
        start = QtCore.QPoint(vp_rect.width() - 2, vp_rect.height() - 2)
        assert not thumbs.indexAt(start).isValid(), "起点必须落在空白处"
        before = tags()
        thumbs.clearSelection()
        pump(app, 20)
        QTest.mousePress(vp, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, start)
        pump(app, 20)
        picked = set()
        pos = start
        for step in range(1, 10):
            pos = QtCore.QPoint(max(2, start.x() - step * 24),
                                max(2, start.y() - step * 76))
            QTest.mouseMove(vp, pos)
            pump(app, 20)
            assert thumbs._drag_mode == thumbs._DRAG_BAND, \
                ("空白处拖动应判为框选，实际 %r" % thumbs._drag_mode)
            assert thumbs._drop_row is None, "框选时不该算拖拽落点"
            picked = {thumbs.row(it) for it in thumbs.selectedItems()}
        QTest.mouseRelease(vp, Qt.LeftButton, Qt.KeyboardModifier.NoModifier, pos)
        pump(app, 200)
        assert tags() == before, ("框选不该改变页序", tags())
        assert picked, "框选应该选中框内的页面"
        assert thumbs._band_rect is None, "松手后框选矩形要清掉"
        assert thumbs._drop_row is None

    check("缩略图拖拽与框选互不干扰", t_thumbs_gesture_split)

    # ---------------- 合并对话框 ----------------
    from pdfstudio.ui.merge_dialog import MergeDialog, MERGE_THUMB_W, MERGE_THUMB_H  # noqa: E402

    def make_tags_pdf(path, count, tag):
        """每页只写一行 "TAG-n"，方便按文字反查页序。"""
        import pymupdf as fitz
        d = fitz.open()
        for i in range(count):
            page = d.new_page(width=595, height=842)
            page.insert_text((72, 100), "%s-%d" % (tag, i + 1),
                             fontsize=28, fontname="helv")
        d.save(path, garbage=3, deflate=True)
        d.close()
        return path

    merge_a = make_tags_pdf(os.path.join(OUT, "merge_a.pdf"), 3, "A")
    merge_b = make_tags_pdf(os.path.join(OUT, "merge_b.pdf"), 2, "B")

    def settle_merge(dlg, limit=6.0):
        end = time.time() + limit
        while time.time() < end:
            app.processEvents()
            if not dlg.page_list._pending:
                break
            time.sleep(0.01)
        app.processEvents()

    def open_merge(paths=None):
        dlg = hide_offscreen(MergeDialog(win))
        dlg.show()
        pump(app, 60)
        if paths:
            dlg.add_paths(paths)
            pump(app, 150)
        return dlg

    def without_confirm(fn):
        """临时把「是 / 否」确认框改成自动点「是」，测试里不能卡在模态框上。"""
        original = QtWidgets.QMessageBox.question
        QtWidgets.QMessageBox.question = staticmethod(
            lambda *args, **kwargs: QtWidgets.QMessageBox.Yes)
        try:
            return fn()
        finally:
            QtWidgets.QMessageBox.question = original

    def t_merge_add():
        dlg = open_merge([merge_a, merge_b])
        try:
            assert dlg.plan.file_count == 2, dlg.plan.file_count
            assert dlg.plan.total_pages == 5, dlg.plan.total_pages
            assert dlg.page_list.count() == 5, dlg.page_list.count()
            assert dlg.src_list.count() == 2, dlg.src_list.count()
            texts = [dlg.page_list.item(i).text() for i in range(5)]
            assert texts == ["第 %d 页" % (i + 1) for i in range(5)], texts
            assert dlg.btn_ok.isEnabled()
            # 每个格子都必须先有占位图，否则 sizeHint 塌陷会拖垮整列
            for i in range(5):
                assert not dlg.page_list.item(i).icon().isNull(), i
        finally:
            dlg.reject()
            pump(app, 50)

    check("合并窗口：添加文件", t_merge_add)

    def t_merge_reorder():
        """拖拽排序后，模型顺序、编号、缩略图三者必须同时对上。

        走 apply_drop —— 生产代码里 dropEvent 算完落点就调它。
        真实的"按住鼠标拖过去"在自动化里造不出来（QDrag::exec 是平台级事件循环），
        但"落点算得对不对、搬完收尾做没做"才是会出错的地方。

        **故意不等缩略图画完就拖**：图标是挂在 item 上的，会跟着 item 一起搬，
        画完了再拖根本测不出问题；只有"还有没画的页"时，渲染队列如果按旧行号
        去画，才会画到别人身上（串页）。
        """
        dlg = hide_offscreen(MergeDialog(win))
        dlg.show()
        pump(app, 30)
        dlg.add_paths([merge_a, merge_b])
        lst = dlg.page_list
        assert lst._pending, "需要保留未渲染的页，否则测不出串页"
        try:
            # 把第 1 格拖到第 4 格后面：target 用"原始行号"表示插入点
            assert lst.apply_drop([0], 4) is True, "往后拖应该真的搬动"
            pump(app, 80)

            assert dlg.plan.order == [(0, 1), (0, 2), (1, 0), (0, 0), (1, 1)], dlg.plan.order
            texts = [lst.item(i).text() for i in range(lst.count())]
            assert texts == ["第 %d 页" % (i + 1) for i in range(5)], texts

            # 等队列跑完，逐格比对：每一格显示的必须是自己那一页
            settle_merge(dlg)
            for row in range(lst.count()):
                key = lst.item(row).data(QtCore.Qt.UserRole)
                want = lst._pixmap_for(key).toImage()
                got = lst.item(row).icon().pixmap(MERGE_THUMB_W, MERGE_THUMB_H).toImage()
                assert got.size() == want.size(), (row, got.size(), want.size())
                assert got == want, "第 %d 格（%s）显示的页不对" % (row + 1, key)

            # 反过来再拖回去，模型要能跟得上
            assert lst.apply_drop([3], 0) is True
            pump(app, 80)
            assert dlg.plan.order == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1)], dlg.plan.order

            # 原地放下不算移动：不能白搬一趟（白搬会把选中状态抖掉）
            assert lst.apply_drop([2], 2) is False, "原地放下应该判成没动"
        finally:
            dlg.reject()
            pump(app, 50)

    check("合并窗口：拖拽排序后模型与缩略图一致", t_merge_reorder)

    def t_merge_drop_placement():
        """落点换算：往前拖、往后拖、多选一起拖、拖到末尾。"""
        from pdfstudio.ui.merge_dialog import drop_placement, is_noop_move

        # 第 1 格拖到第 2 格后半 → 插到原第 3 行前面，也就是搬走之后的下标 1
        assert drop_placement(5, [0], 2) == ([0], 1)
        # 第 1 格拖到最前 → 不动
        moving, at = drop_placement(5, [0], 0)
        assert (moving, at) == ([0], 0) and is_noop_move(moving, at)
        # 最后一格拖到最前
        assert drop_placement(5, [4], 0) == ([4], 0)
        # 拖到末尾
        assert drop_placement(5, [0], 5) == ([0], 4)
        # 连着的两格一起往后拖
        assert drop_placement(6, [1, 2], 5) == ([1, 2], 3)
        # 多选不连续：搬走两行之后目标位置要减 2 里排在它前面的那些
        assert drop_placement(6, [1, 4], 6) == ([1, 4], 4)
        # 空选择 / 越界行号不能炸
        assert drop_placement(5, [], 3) == ([], 0)
        assert drop_placement(5, [9], 3) == ([], 0)

    check("合并窗口：拖拽落点换算", t_merge_drop_placement)

    def t_merge_drop_target():
        """光标落在格子的前半还是后半，决定插到它前面还是后面。

        这条以前是"能拖但拖了没反应"的根源之一：只判"插到悬停项前面"的话，
        把第 1 格拖到第 2 格上等于原地不动，用户看到的就是拖不动。
        """
        dlg = open_merge([merge_a])
        try:
            lst = dlg.page_list
            pump(app, 60)
            rect = lst.visualItemRect(lst.item(0))
            assert rect.isValid() and rect.width() > 10, rect
            before = rect.topLeft() + QtCore.QPoint(4, 4)
            after = rect.bottomRight() - QtCore.QPoint(4, 4)
            assert lst._drop_target(before) == 0, lst._drop_target(before)
            assert lst._drop_target(after) == 1, lst._drop_target(after)
            # 落在空白处 → 追加到末尾
            empty = QtCore.QPoint(lst.viewport().width() - 5,
                                  lst.viewport().height() - 5)
            assert lst._drop_target(empty) == lst.count(), lst._drop_target(empty)
        finally:
            dlg.reject()
            pump(app, 50)

    check("合并窗口：落点在格子前后半的判断", t_merge_drop_target)

    def t_merge_delete():
        dlg = open_merge([merge_a, merge_b])
        try:
            lst = dlg.page_list
            for row in (1, 3):            # 删掉 A-2 和 B-1
                lst.item(row).setSelected(True)
            dlg.delete_selected()
            pump(app, 100)

            assert dlg.plan.total_pages == 3, dlg.plan.total_pages
            assert lst.count() == 3, lst.count()
            assert dlg.plan.order == [(0, 0), (0, 2), (1, 1)], dlg.plan.order
            texts = [lst.item(i).text() for i in range(3)]
            assert texts == ["第 1 页", "第 2 页", "第 3 页"], texts
            # 源文件清单要显示还剩几页
            assert "2 / 3 页" in dlg.src_list.item(0).text(), dlg.src_list.item(0).text()
            assert "1 / 2 页" in dlg.src_list.item(1).text(), dlg.src_list.item(1).text()
        finally:
            dlg.reject()
            pump(app, 50)

    check("合并窗口：删除选中页", t_merge_delete)

    def t_merge_remove_source():
        """移除文件后源下标会整体前移，旧条目的 (源, 页) 必须重挂，否则指向错的文件。"""
        dlg = open_merge([merge_a, merge_b])
        try:
            dlg.src_list.setCurrentRow(0)
            without_confirm(dlg.remove_current_source)
            pump(app, 120)

            assert dlg.plan.file_count == 1, dlg.plan.file_count
            assert dlg.plan.total_pages == 2, dlg.plan.total_pages
            keys = [dlg.page_list.item(i).data(QtCore.Qt.UserRole)
                    for i in range(dlg.page_list.count())]
            assert keys == [(0, 0), (0, 1)], keys
            assert dlg.src_list.count() == 1
            # 剩下的必须是 B 的两页
            settle_merge(dlg)
            got = dlg.page_list.item(0).icon().pixmap(MERGE_THUMB_W, MERGE_THUMB_H).toImage()
            want = dlg.page_list._pixmap_for((0, 0)).toImage()
            assert got == want
        finally:
            dlg.reject()
            pump(app, 50)

    check("合并窗口：移除源文件后重新挂载", t_merge_remove_source)

    def t_merge_drop_url():
        """从资源管理器把 PDF 拖进窗口。"""
        dlg = open_merge()
        try:
            mime = QtCore.QMimeData()
            mime.setUrls([QtCore.QUrl.fromLocalFile(merge_b)])
            event = QtGui.QDropEvent(
                QtCore.QPoint(30, 30), Qt.DropAction.MoveAction, mime,
                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            dlg.page_list.dropEvent(event)
            pump(app, 150)
            assert dlg.plan.file_count == 1, dlg.plan.file_count
            assert dlg.plan.total_pages == 2, dlg.plan.total_pages
            assert dlg.page_list.count() == 2
        finally:
            dlg.reject()
            pump(app, 50)

    check("合并窗口：拖入外部 PDF 文件", t_merge_drop_url)

    def t_merge_real_mouse_drag():
        """真实鼠标按下 -> 移动 -> 松手，页序必须真的变。

        这是唯一能证明"拖得动"的测法。以前这条链路上有 QDrag::exec，
        它是平台级模态循环，测试根本进不去，所以只能退而求其次去断言
        "dragEnabled 是不是 True"——而真正的故障（exec 进去回不来）
        在这类断言面前完全隐形，连着两轮"修复 + 全绿 + 用户还是拖不动"。

        现在拖拽自己实现（mousePress/mouseMove/mouseRelease），没有模态
        循环，可以用 QTest 发真实鼠标事件把整条链路完整走一遍。
        """
        from PySide6.QtTest import QTest

        dlg = open_merge([merge_a, merge_b])
        try:
            lst = dlg.page_list
            pump(app, 80)
            assert lst.count() >= 5, lst.count()
            before = lst.current_keys()

            def drag(src_row, dst_row, half="back"):
                rect = lst.visualItemRect(lst.item(dst_row))
                press = lst.visualItemRect(lst.item(src_row)).center()
                if half == "back":
                    target = QtCore.QPoint(rect.right() - 6, rect.center().y())
                else:
                    target = QtCore.QPoint(rect.left() + 6, rect.center().y())
                QTest.mousePress(lst.viewport(), Qt.LeftButton,
                                 Qt.KeyboardModifier.NoModifier, press)
                pump(app, 2)
                steps = 6
                for step in range(1, steps + 1):
                    pos = QtCore.QPoint(
                        press.x() + (target.x() - press.x()) * step // steps,
                        press.y() + (target.y() - press.y()) * step // steps)
                    QTest.mouseMove(lst.viewport(), pos)
                    pump(app, 2)
                QTest.mouseRelease(lst.viewport(), Qt.LeftButton,
                                   Qt.KeyboardModifier.NoModifier, target)
                pump(app, 3)

            # 1) 往后拖：第 1 格拖到第 4 格后半 —— 以前这里就是"松手没反应"
            drag(0, 3)
            after = lst.current_keys()
            assert after != before, "松手后页序没变：拖拽没生效（%r）" % (after,)
            # 模型必须跟着走，否则界面对了、写出来的文件还是旧顺序
            assert dlg.plan.order == after, (dlg.plan.order, after)
            assert [it.text() for it in lst.selectedItems()] == ["第 4 页"], \
                [it.text() for it in lst.selectedItems()]

            # 2) 往前拖：最后一格拖到第 1 格前半
            before = lst.current_keys()
            drag(lst.count() - 1, 0, half="front")
            after = lst.current_keys()
            assert after != before, "往前拖没生效"
            assert dlg.plan.order == after

            # 3) 拖回原地：顺序不该变，但也不能报错或卡住
            before = lst.current_keys()
            drag(2, 2, half="front")
            assert lst.current_keys() == before, "拖回原地不该改变顺序"

            # 4) 只是点一下（没超过拖拽阈值）不能搬行，否则点选就误操作
            before = lst.current_keys()
            centre = lst.visualItemRect(lst.item(1)).center()
            QTest.mousePress(lst.viewport(), Qt.LeftButton,
                             Qt.KeyboardModifier.NoModifier, centre)
            QTest.mouseRelease(lst.viewport(), Qt.LeftButton,
                               Qt.KeyboardModifier.NoModifier, centre)
            pump(app, 3)
            assert lst.current_keys() == before, "单击不该搬行"

            # 5) 拖完不能再有残留状态（否则下一次点击会被当成继续拖）
            assert lst._drag_start is None and not lst._dragging
            assert lst._drop_row is None, "落点标记要在松手后清掉"
        finally:
            dlg.reject()
            pump(app, 50)

    check("合并窗口：真实鼠标拖拽能搬行", t_merge_real_mouse_drag)

    def t_merge_build():
        out = os.path.join(OUT, "ui_merged.pdf")
        if os.path.exists(out):
            os.remove(out)
        dlg = open_merge([merge_a, merge_b])
        try:
            lst = dlg.page_list
            assert lst.apply_drop([4], 0) is True   # 把 B-2 拖到最前面
            pump(app, 60)

            dlg.out_edit.setText(out)
            dlg.run_merge()
            pump(app, 150)
            assert dlg.result_path() == out, dlg.result_path()
        finally:
            dlg.close()

        import pymupdf as fitz
        d = fitz.open(out)
        try:
            tags = [p.get_text("text").strip() for p in d]
        finally:
            d.close()
        assert tags == ["B-2", "A-1", "A-2", "A-3", "B-1"], tags

    check("合并窗口：拖拽后写出文件页序正确", t_merge_build)

    def t_merge_empty_state():
        dlg = open_merge()
        try:
            assert not dlg.btn_ok.isEnabled(), "没有页面时不该能点「开始合并」"
            assert dlg.page_list.count() == 0
        finally:
            dlg.reject()
            pump(app, 50)

    check("合并窗口：空状态按钮禁用", t_merge_empty_state)

    def t_close():
        win.doc.dirty = False
        win.close()
        pump(app, 100)

    check("关闭窗口", t_close)

    print("\n通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失败项：", [f[0] for f in FAIL])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
