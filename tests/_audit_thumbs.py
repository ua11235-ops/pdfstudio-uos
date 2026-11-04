# -*- coding: utf-8 -*-
"""缩略图面板审计：把所有会改变页面数量/顺序的操作挨个跑一遍，
检查缩略图列表的状态是否始终和文档一致。

只在开发时手动运行，用来一次性找出所有同类问题。
"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pdfstudio.qtcompat import QtWidgets, Qt  # noqa: E402
from _thumb_probe import (THUMB_WIDTH, THUMB_HEIGHT, TOLERANCE,  # noqa: E402
                          grid_signature, page_signature, mismatch,
                          make_color_pdf, make_mixed_pdf, pump, settle)
from pdfstudio.ui import theme  # noqa: E402
from pdfstudio.ui.main_window import MainWindow  # noqa: E402
from pdfstudio.core import pageops  # noqa: E402

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

OUT = os.path.join(ROOT, "screenshots", "_test")
os.makedirs(OUT, exist_ok=True)

TOTAL = []
BAD = []

def make_sample(pages=12):
    """现造一份多页 PDF。

    samples/sample.pdf 只有两页，删除/移动/多页删除这些场景全都会退化，
    审计必须用页数够多的文档才有意义。
    """
    return make_color_pdf(
        os.path.join(tempfile.gettempdir(), "audit_thumbs_%d.pdf" % pages),
        pages)


def audit(win, tag, app, shot=None):
    """检查缩略图面板与文档是否一致，返回问题列表。"""
    # 侧栏刷新有防抖、缩略图还要逐张渲染，必须等两者都落地再判断，
    # 否则测出来的是"还没刷新"，不是真的错。
    settle(app, win)

    th = win.side.thumbs
    doc = win.doc
    problems = []

    if th.count() != doc.page_count:
        problems.append("条目数 %d != 页数 %d" % (th.count(), doc.page_count))

    for i in range(min(th.count(), doc.page_count)):
        it = th.item(i)
        if it is None:
            problems.append("item%d 为 None" % i)
            continue
        if it.icon().isNull():
            problems.append("item%d 无图标" % i)
        data = it.data(Qt.UserRole)
        if data != i:
            problems.append("item%d 的 UserRole=%r" % (i, data))
        want = "第 %d 页" % (i + 1)
        if it.text() != want:
            problems.append("item%d 文字=%r 期望 %r" % (i, it.text(), want))

    if th.count():
        r = th.visualItemRect(th.item(0))
        if r.height() < 100:
            problems.append("item0 被压扁 %dx%d" % (r.width(), r.height()))

    # 内容校验：缩略图画的必须是它自己那一页。
    # 页面内容变了（插入/删除/换序）但条目没重绘，布局检查是发现不了的。
    for i in range(min(th.count(), doc.page_count)):
        worst = mismatch(doc, th.item(i), i)
        if worst is not None and worst > TOLERANCE:
            problems.append(
                "item%d 缩略图内容与第 %d 页不符（最大色差 %d，"
                "待渲染 %d 项，定时器%s）"
                % (i, i + 1, worst, len(th._pending),
                   "运行中" if th._timer.isActive() else "已停"))
            break

    # 当前页要和正文视图对上
    if th.currentRow() != win.page_view.page_index:
        problems.append("当前行 %d != 视图页 %d"
                        % (th.currentRow(), win.page_view.page_index))

    if shot:
        win.grab().save(os.path.join(OUT, shot))

    mark = "OK " if not problems else "BAD"
    print("  [%s] %-30s 页数=%-3d 条目=%-3d 当前行=%s"
          % (mark, tag, doc.page_count, th.count(), th.currentRow()))
    for p in problems:
        print("        - %s" % p)
        BAD.append("%s: %s" % (tag, p))
    TOTAL.append(tag)
    return problems


def check_uniform(win, tag):
    """检查所有格子尺寸一致、图标尺寸固定。

    页面长宽比一变，按宽度算缩放就会得到不同高度的图标，
    格子被撑高、间距忽大忽小、图还会被二次缩放得像裁掉了上下。
    这条线必须守住：不管什么比例的页，图标都必须是同一块画布。
    """
    th = win.side.thumbs
    problems = []
    sizes = set()
    rects = set()
    for i in range(th.count()):
        item = th.item(i)
        if item is None:
            problems.append("%s: item%d 为 None" % (tag, i))
            continue
        pm = item.icon().pixmap(THUMB_WIDTH, THUMB_HEIGHT)
        sizes.add((pm.width(), pm.height()))
        r = th.visualItemRect(item)
        if r.height() > 0:
            rects.add((r.width(), r.height()))
        worst = mismatch(win.doc, item, i)
        if worst is not None and worst > TOLERANCE:
            problems.append("%s: item%d 画错页（色差 %d）" % (tag, i, worst))
    if sizes != {(THUMB_WIDTH, THUMB_HEIGHT)}:
        problems.append("%s: 图标尺寸不统一 %s" % (tag, sorted(sizes)))
    if len(rects) > 1:
        problems.append("%s: 格子尺寸不统一 %s" % (tag, sorted(rects)))

    mark = "OK " if not problems else "BAD"
    print("  [%s] %-30s 图标=%s 格子=%s"
          % (mark, tag, sorted(sizes), sorted(rects)))
    for p in problems:
        print("        - %s" % p)
    return problems


def main():
    sample = make_sample(12)

    app = QtWidgets.QApplication(sys.argv)
    theme.apply(app)
    win = MainWindow()
    win.setAttribute(Qt.WA_DontShowOnScreen, True)
    win.resize(1400, 900)
    win.show()
    pump(app, 300)

    win.open_path(sample)
    pump(app, 900)
    print("\n初始文档 %d 页" % win.doc.page_count)
    audit(win, "初始", app, "audit_00_init.png")

    # ---- 插入空白页：开头 / 中间 / 末尾 ----
    win.insert_blank_after(0)
    audit(win, "在首页后插入空白页", app)

    win.insert_blank_after(win.doc.page_count - 1)
    audit(win, "在末页后插入空白页", app)

    mid = win.doc.page_count // 2
    win.insert_blank_after(mid)
    audit(win, "在中间插入空白页", app, "audit_01_insert.png")

    # 连插三页，模拟用户快速连点
    for _ in range(3):
        win.insert_blank_after(0)
        pump(app, 60)
    audit(win, "快速连插 3 页", app)

    # ---- 从文件插入多页 ----
    win.doc.begin_change("插入文件")
    pageops.insert_from_file(win.doc, sample, 1)
    win.doc.end_change()
    audit(win, "从文件插入多页", app, "audit_02_insert_file.png")

    # ---- 删除：中间 / 第一页 / 最后一页 / 多页 ----
    win.delete_pages([win.doc.page_count // 2])
    audit(win, "删除中间页", app, "audit_03_delete_mid.png")

    win.delete_pages([0])
    audit(win, "删除第一页", app, "audit_04_delete_first.png")

    win.delete_pages([win.doc.page_count - 1])
    audit(win, "删除最后一页", app, "audit_05_delete_last.png")

    win.delete_pages([1, 2, 3])
    audit(win, "删除多页", app, "audit_06_delete_multi.png")

    win.delete_pages([0, 1])
    audit(win, "删除开头连续两页", app)

    # ---- 旋转 / 移动 ----
    win.rotate_pages([0], 90)
    audit(win, "旋转第一页", app, "audit_07_rotate.png")

    win.move_page_by(0, 1)
    audit(win, "下移一页", app)

    win.move_page_by(1, -1)
    audit(win, "上移一页", app)

    win.move_page_to(0, win.doc.page_count - 1)
    audit(win, "移到文档末尾", app, "audit_08_move.png")

    win.move_page_to(win.doc.page_count - 1, 0)
    audit(win, "移到文档开头", app)

    # ---- 撤销到底 / 重做到底 ----
    for _ in range(60):
        if not win.doc.can_undo():
            break
        win.undo()
        pump(app, 80)
    audit(win, "撤销到底", app, "audit_09_undo_all.png")

    for _ in range(60):
        if not win.doc.can_redo():
            break
        win.redo()
        pump(app, 80)
    audit(win, "重做到底", app, "audit_10_redo_all.png")

    # ---- 删到只剩一页 ----
    if win.doc.page_count > 1:
        win.delete_pages(list(range(1, win.doc.page_count)))
        audit(win, "删到只剩一页", app, "audit_11_one_page.png")

    # 只剩一页时再插入，边界场景
    win.insert_blank_after(0)
    audit(win, "只剩一页后再插入", app)

    # ---- 关闭文档 ----
    win.doc.close()
    pump(app, 600)
    if win.side.thumbs.count() != 0:
        BAD.append("关闭文档: 条目数残留 %d" % win.side.thumbs.count())
        print("  [BAD] 关闭文档                          条目残留=%d"
              % win.side.thumbs.count())
    else:
        print("  [OK ] 关闭文档                          列表已清空")
    TOTAL.append("关闭文档")

    # ---- 大文档：屏幕上的那几页要先出图 ----
    big = make_sample(200)
    win.open_path(big)
    pump(app, 400)
    th = win.side.thumbs

    def ready_count(indices):
        n = 0
        for i in indices:
            worst = mismatch(win.doc, th.item(i), i)
            if worst is not None and worst <= TOLERANCE:
                n += 1
        return n

    ready = ready_count(range(6))
    print("  [%s] %-30s 400ms 内可见区已出图 %d/6，队列还剩 %d"
          % ("OK " if ready >= 5 else "BAD", "大文档可见区优先",
             ready, len(th._pending)))
    TOTAL.append("大文档可见区优先")
    if ready < 5:
        BAD.append("大文档可见区优先: 只有 %d/6 张图就绪" % ready)

    # 滚到第 150 页，那里本该是灰块，改完之后应该很快出图
    th.scrollToItem(th.item(150))
    pump(app, 400)
    view = th.viewport().rect()
    visible = [i for i in range(th.count())
               if view.intersects(th.visualItemRect(th.item(i)))]
    ready2 = ready_count(visible)
    print("  [%s] %-30s 滚到第 150 页后 400ms 出图 %d/%d"
          % ("OK " if ready2 >= len(visible) - 1 else "BAD",
             "滚动后可见区优先", ready2, len(visible)))
    TOTAL.append("滚动后可见区优先")
    if ready2 < len(visible) - 1:
        BAD.append("滚动后可见区优先: 只有 %d/%d 张图就绪" % (ready2, len(visible)))

    # ---- 页面尺寸混杂：格子尺寸不能被页面比例带跑 ----
    mixed = make_mixed_pdf(os.path.join(tempfile.gettempdir(), "audit_mixed.pdf"))
    win.open_path(mixed)
    settle(app, win)
    mixed_bad = check_uniform(win, "混合页面尺寸")
    win.delete_pages([2])
    settle(app, win)
    mixed_bad += check_uniform(win, "混合尺寸删页后")
    if mixed_bad:
        BAD.extend(mixed_bad)
    TOTAL.extend(["混合页面尺寸", "混合尺寸删页后"])

    print("\n" + "=" * 60)
    if BAD:
        print("发现 %d 个问题：" % len(BAD))
        for b in BAD:
            print("  - %s" % b)
    else:
        print("全部 %d 个场景正常" % len(TOTAL))
    print("=" * 60)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
