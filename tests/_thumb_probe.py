# -*- coding: utf-8 -*-
"""缩略图校验工具：判断列表里的缩略图是不是真的画对了页。

布局检查（条目数、矩形尺寸）只能发现"挤成一条"这类问题，
画错页、没刷新、还停在灰色占位图上这些，必须比对图像内容。
"""

import time

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from pdfstudio.qtcompat import QtGui, RGB888
from pdfstudio.ui.side_panel import (THUMB_WIDTH, THUMB_HEIGHT,
                                     render_page_pixmap)

# 分格平均后的容差。太小会因缩放插值误报，太大会漏掉空白页与有内容页的差别。
TOLERANCE = 34

# 每页顶部刷一条独占的颜色带，缩略图内容对不对就能一眼验出来。
# 用普通文档的话每页都是白底黑字，粗粒度指纹分不出来，
# "缩略图画成别的页"这种错就抓不住。
PALETTE = [
    (214, 48, 49), (0, 121, 140), (56, 103, 214), (43, 138, 62),
    (198, 120, 0), (128, 60, 152), (0, 130, 160), (170, 60, 90),
    (90, 120, 30), (60, 60, 180), (200, 90, 20), (30, 140, 110),
    (150, 40, 40), (40, 90, 150), (110, 90, 20), (80, 40, 110),
]


def make_color_pdf(path, pages=12):
    """造一份每页颜色都不同的多页 PDF，用作缩略图校验的素材。"""
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        r, g, b = PALETTE[i % len(PALETTE)]
        page.draw_rect(fitz.Rect(0, 0, 595, 260),
                       color=None, fill=(r / 255.0, g / 255.0, b / 255.0))
        page.insert_text((72, 400), "Page %d" % (i + 1), fontsize=48)
    doc.save(path)
    doc.close()
    return path


# 公文里常见的几种页面尺寸：标准 A4、长条页、横向表格页、小页
MIXED_SIZES = [
    (595, 842), (595, 842), (595, 980), (595, 842),
    (842, 595), (595, 842), (420, 595), (595, 1200),
    (595, 842), (595, 842),
]


def make_mixed_pdf(path):
    """造一份页面尺寸混杂的 PDF。

    只要有一页长宽比和 A4 不同，按宽度算缩放就会得到不同尺寸的图标，
    进而把格子撑高、间距拉乱。这份素材专门用来守这条线。
    """
    doc = fitz.open()
    for i, (w, h) in enumerate(MIXED_SIZES):
        page = doc.new_page(width=w, height=h)
        r, g, b = PALETTE[i % len(PALETTE)]
        page.draw_rect(fitz.Rect(0, 0, w, h * 0.3),
                       color=None, fill=(r / 255.0, g / 255.0, b / 255.0))
        page.insert_text((30, h * 0.5), "Page %d" % (i + 1), fontsize=30)
    doc.save(path)
    doc.close()
    return path


def grid_signature(img):
    """把图缩成 4x4 的粗粒度颜色指纹，取不到返回 None。"""
    w, h = img.width(), img.height()
    if w < 8 or h < 8:
        return None
    sig = []
    for gy in range(4):
        y0, y1 = h * gy // 4, h * (gy + 1) // 4
        for gx in range(4):
            x0, x1 = w * gx // 4, w * (gx + 1) // 4
            sx = max(1, (x1 - x0) // 8)
            sy = max(1, (y1 - y0) // 8)
            total = [0, 0, 0]
            n = 0
            for y in range(y0, y1, sy):
                for x in range(x0, x1, sx):
                    c = img.pixelColor(x, y)
                    total[0] += c.red()
                    total[1] += c.green()
                    total[2] += c.blue()
                    n += 1
            sig.append(tuple(v // n for v in total) if n else (0, 0, 0))
    return sig


def page_signature(doc, index):
    """按界面里同一套逻辑，算出这一页的缩略图应该长什么样。

    必须直接调用 side_panel 的渲染函数，不能自己再写一遍缩放公式——
    两边一旦不一致，校验就会开始误报或者漏报。
    """
    try:
        return grid_signature(render_page_pixmap(doc.doc[index]).toImage())
    except Exception:
        return None


def item_signature(item):
    if item is None:
        return None
    return grid_signature(item.icon().pixmap(THUMB_WIDTH, THUMB_HEIGHT).toImage())


def mismatch(doc, item, index):
    """返回缩略图与第 index 页的最大色差，取不到值时返回 None。"""
    got = item_signature(item)
    want = page_signature(doc, index)
    if got is None or want is None:
        return None
    worst = 0
    for a, b in zip(got, want):
        worst = max(worst, max(abs(x - y) for x, y in zip(a, b)))
    return worst


def pump(app, ms=200):
    """跑一段时间的事件循环，让界面把该刷新的都刷完。"""
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def settle(app, win, limit=8.0, debounce=420):
    """等侧栏刷新落地、缩略图渲染队列清空。

    侧栏刷新有 350ms 防抖，缩略图又是一张一张画的，页数一多就要好几百毫秒。
    固定等一个时长会测出"还在画"的假故障，必须盯着队列等它空。
    """
    pump(app, debounce)
    th = win.side.thumbs
    end = time.time() + limit
    while time.time() < end:
        app.processEvents()
        if not th._pending and not th._timer.isActive():
            break
        time.sleep(0.005)
    app.processEvents()
