# -*- coding: utf-8 -*-
"""各类对话框。全部继承自 BaseDialog，保持一致的排版与按钮行为。"""

from ..qtcompat import QtCore, QtGui, QtWidgets, Qt, qexec

from .. import APP_NAME, APP_NAME_CN, __version__
from . import icons
from .theme import COLORS


class BaseDialog(QtWidgets.QDialog):
    def __init__(self, title, parent=None, width=420):
        QtWidgets.QDialog.__init__(self, parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(width)
        self.setWindowIcon(QtGui.QIcon(icons.app_icon(64)))

        self._outer = QtWidgets.QVBoxLayout(self)
        self._outer.setContentsMargins(20, 18, 20, 16)
        self._outer.setSpacing(14)

        self.heading = QtWidgets.QLabel(title)
        font = self.heading.font()
        font.setPointSize(font.pointSize() + 2)
        font.setBold(True)
        self.heading.setFont(font)
        self._outer.addWidget(self.heading)

        self._form = QtWidgets.QFormLayout()
        self._form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._form.setHorizontalSpacing(14)
        self._form.setVerticalSpacing(10)
        self._outer.addLayout(self._form)

        self._extra = QtWidgets.QVBoxLayout()
        self._outer.addLayout(self._extra)

        self._outer.addStretch(1)

        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("确定")
        self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setDefault(True)
        self.buttons.button(QtWidgets.QDialogButtonBox.Cancel).setText("取消")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self._outer.addWidget(self.buttons)

    def add_row(self, label, widget):
        self._form.addRow(label, widget)
        return widget

    def add_widget(self, widget):
        self._extra.addWidget(widget)
        return widget

    def add_hint(self, text):
        label = QtWidgets.QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("color: %s; font-size: 12px;" % COLORS["text_sub"])
        self._extra.addWidget(label)
        return label

    def exec_dialog(self):
        return qexec(self) == QtWidgets.QDialog.Accepted


def _spin(minimum, maximum, value, suffix="", decimals=0):
    if decimals:
        widget = QtWidgets.QDoubleSpinBox()
        widget.setDecimals(decimals)
        widget.setSingleStep(0.5)
    else:
        widget = QtWidgets.QSpinBox()
    widget.setRange(minimum, maximum)
    widget.setValue(value)
    if suffix:
        widget.setSuffix(suffix)
    return widget


def _combo(items):
    box = QtWidgets.QComboBox()
    for label, value in items:
        box.addItem(label, value)
    return box


# ----------------------------------------------------------------------
class TextInputDialog(BaseDialog):
    def __init__(self, title, label, text="", parent=None, height=110):
        BaseDialog.__init__(self, title, parent, 460)
        self.heading.setText(title)
        self.add_hint(label)
        self.editor = QtWidgets.QPlainTextEdit()
        self.editor.setPlainText(text or "")
        self.editor.setMinimumHeight(height)
        self.editor.selectAll()
        self.add_widget(self.editor)
        self.editor.setFocus()

    def text_value(self):
        return self.editor.toPlainText()


class WatermarkDialog(BaseDialog):
    def __init__(self, parent=None):
        BaseDialog.__init__(self, "添加水印", parent, 460)
        self.text = self.add_row("水印文字", QtWidgets.QLineEdit("内部资料"))
        self.text.setPlaceholderText("例如：内部资料 / 机密 / 草稿")
        self.font_size = self.add_row("字号", _spin(10, 200, 48, " pt"))
        self.opacity = self.add_row("透明度", _spin(5, 100, 18, " %"))
        self.angle = self.add_row("倾斜角度", _spin(-90, 90, 45, " °"))
        self.mode = self.add_row("排布方式", _combo([("居中单个", "sparse"), ("整页平铺", "dense")]))
        self.color = self.add_row("颜色", _color_combo([
            ("浅灰", (0.55, 0.55, 0.55)),
            ("深灰", (0.30, 0.30, 0.30)),
            ("红色", (0.85, 0.20, 0.20)),
            ("蓝色", (0.15, 0.35, 0.80)),
        ]))
        self.scope = self.add_row("应用范围", _combo([("全部页面", "all"), ("仅当前页", "current")]))
        self.add_hint("水印会写入页面内容，导出和打印时都会保留。")

    def values(self):
        return {
            "text": self.text.text().strip(),
            "font_size": self.font_size.value(),
            "opacity": self.opacity.value() / 100.0,
            "angle": self.angle.value(),
            "mode": self.mode.currentData(),
            "color": self.color.currentData(),
            "scope": self.scope.currentData(),
        }


class PageNumberDialog(BaseDialog):
    def __init__(self, parent=None):
        BaseDialog.__init__(self, "添加页码", parent, 460)
        self.position = self.add_row("位置", _combo([
            ("底部居中", "bottom_center"), ("底部靠左", "bottom_left"), ("底部靠右", "bottom_right"),
            ("顶部居中", "top_center"), ("顶部靠左", "top_left"), ("顶部靠右", "top_right"),
        ]))
        self.template = self.add_row("格式", QtWidgets.QLineEdit("第 {page} 页 / 共 {total} 页"))
        self.start = self.add_row("起始页码", _spin(1, 9999, 1))
        self.font_size = self.add_row("字号", _spin(6, 48, 10, " pt"))
        self.skip_first = self.add_row("", QtWidgets.QCheckBox("首页不显示页码"))
        self.add_hint("格式中可使用 {page}（当前页）与 {total}（总页数）两个占位符。")

    def values(self):
        return {
            "position": self.position.currentData(),
            "template": self.template.text(),
            "start_number": self.start.value(),
            "font_size": self.font_size.value(),
            "skip_first": self.skip_first.isChecked(),
        }


class EncryptDialog(BaseDialog):
    def __init__(self, parent=None):
        BaseDialog.__init__(self, "加密文档", parent, 460)
        self.user_pw = self.add_row("打开密码", QtWidgets.QLineEdit())
        self.user_pw.setEchoMode(QtWidgets.QLineEdit.Password)
        self.confirm = self.add_row("确认密码", QtWidgets.QLineEdit())
        self.confirm.setEchoMode(QtWidgets.QLineEdit.Password)
        self.owner_pw = self.add_row("权限密码", QtWidgets.QLineEdit())
        self.owner_pw.setEchoMode(QtWidgets.QLineEdit.Password)
        self.owner_pw.setPlaceholderText("可选，留空则与打开密码相同")
        self.allow_print = QtWidgets.QCheckBox("允许打印")
        self.allow_print.setChecked(True)
        self.allow_copy = QtWidgets.QCheckBox("允许复制文字")
        self.allow_modify = QtWidgets.QCheckBox("允许修改内容")
        self.allow_annotate = QtWidgets.QCheckBox("允许添加注释")
        self.allow_annotate.setChecked(True)
        holder = QtWidgets.QWidget()
        box = QtWidgets.QVBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        for widget in (self.allow_print, self.allow_copy, self.allow_modify, self.allow_annotate):
            box.addWidget(widget)
        self.add_row("权限", holder)
        self.add_hint("加密后会另存为新文件，原文件保持不变。")

    def values(self):
        return {
            "user_password": self.user_pw.text(),
            "confirm": self.confirm.text(),
            "owner_password": self.owner_pw.text(),
            "allow_print": self.allow_print.isChecked(),
            "allow_copy": self.allow_copy.isChecked(),
            "allow_modify": self.allow_modify.isChecked(),
            "allow_annotate": self.allow_annotate.isChecked(),
        }


class CompressDialog(BaseDialog):
    def __init__(self, parent=None, current_size=0):
        BaseDialog.__init__(self, "压缩文档", parent, 460)
        self.level = self.add_row("压缩方式", _combo([
            ("标准（无损，清理冗余数据）", "standard"),
            ("强力（重新压缩图片，体积最小）", "strong"),
        ]))
        self.dpi = self.add_row("图片分辨率", _spin(60, 300, 130, " dpi"))
        self.quality = self.add_row("JPEG 质量", _spin(30, 95, 72, " %"))
        self.add_hint(
            "当前文件大小约 %.1f MB。强力模式会把每页转成图片，"
            "文字将无法再被选中，适合扫描件。" % (current_size / 1024.0 / 1024.0)
        )

    def values(self):
        return {
            "level": self.level.currentData(),
            "dpi": self.dpi.value(),
            "quality": self.quality.value(),
        }


class ExportImageDialog(BaseDialog):
    def __init__(self, parent=None):
        BaseDialog.__init__(self, "导出为图片", parent, 460)
        self.dpi = self.add_row("分辨率", _spin(72, 600, 150, " dpi"))
        self.fmt = self.add_row("图片格式", _combo([("PNG（无损）", "png"), ("JPEG（体积小）", "jpeg")]))
        self.scope = self.add_row("导出范围", _combo([("全部页面", "all"), ("仅当前页", "current")]))
        self.add_hint("导出前会询问保存目录，文件名按页码自动编号。")

    def values(self):
        return {
            "dpi": self.dpi.value(),
            "format": self.fmt.currentData(),
            "scope": self.scope.currentData(),
        }


class SplitDialog(BaseDialog):
    def __init__(self, parent=None, page_count=1):
        BaseDialog.__init__(self, "拆分文档", parent, 460)
        self.mode = self.add_row("拆分方式", _combo([
            ("每页一个文件", "each"),
            ("按页码范围", "ranges"),
        ]))
        self.ranges = self.add_row("页码范围", QtWidgets.QLineEdit("1-3, 4-6"))
        self.ranges.setPlaceholderText("例如：1-3, 4-6, 7")
        self.add_hint("文档共 %d 页。拆分结果会保存到您选择的目录中。" % page_count)

    def values(self):
        return {"mode": self.mode.currentData(), "ranges": self.ranges.text()}


class InsertFileDialog(BaseDialog):
    def __init__(self, path, page_count, current_index, parent=None):
        BaseDialog.__init__(self, "插入页面", parent, 480)
        self.path = path
        name = QtWidgets.QLineEdit(path)
        name.setReadOnly(True)
        self.add_row("源文件", name)
        self.range_edit = self.add_row("源页码范围", QtWidgets.QLineEdit("1-%d" % page_count))
        self.position = self.add_row("插入位置", _combo([
            ("当前页之后", "after"), ("当前页之前", "before"), ("文档末尾", "end"),
        ]))
        self.add_hint("源文件共 %d 页。页码从 1 开始，可用 1-3 或 2,5 这样的写法。" % page_count)
        self._current = current_index

    def values(self):
        return {
            "ranges": self.range_edit.text(),
            "position": self.position.currentData(),
            "current_index": self._current,
        }


class FormFillDialog(BaseDialog):
    def __init__(self, widgets, parent=None):
        BaseDialog.__init__(self, "填写表单", parent, 520)
        self._editors = {}
        self.add_hint("该文档包含 %d 个可填写字段。" % len(widgets))
        grid_host = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.addWidget(QtWidgets.QLabel("字段"), 0, 0)
        grid.addWidget(QtWidgets.QLabel("内容"), 0, 1)
        row = 1
        for item in widgets[:60]:
            label = QtWidgets.QLabel("%s（第 %d 页）" % (item["name"] or "(未命名字段)",
                                                        item["page"] + 1))
            label.setStyleSheet("color: %s;" % COLORS["text_sub"])
            editor = QtWidgets.QLineEdit(str(item["value"] or ""))
            grid.addWidget(label, row, 0)
            grid.addWidget(editor, row, 1)
            self._editors[item["key"]] = editor
            row += 1
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(grid_host)
        scroll.setMinimumHeight(min(380, 40 + len(widgets) * 34))
        self.add_widget(scroll)

    def values(self):
        return dict((key, editor.text()) for key, editor in self._editors.items())


class MetadataDialog(BaseDialog):
    def __init__(self, meta, parent=None):
        BaseDialog.__init__(self, "文档属性", parent, 460)
        self.title_edit = self.add_row("标题", QtWidgets.QLineEdit(meta.get("title", "") or ""))
        self.author = self.add_row("作者", QtWidgets.QLineEdit(meta.get("author", "") or ""))
        self.subject = self.add_row("主题", QtWidgets.QLineEdit(meta.get("subject", "") or ""))
        self.keywords = self.add_row("关键词", QtWidgets.QLineEdit(meta.get("keywords", "") or ""))
        creator = QtWidgets.QLineEdit(meta.get("creator", "") or "")
        creator.setReadOnly(True)
        self.add_row("创建工具", creator)
        producer = QtWidgets.QLineEdit(meta.get("producer", "") or "")
        producer.setReadOnly(True)
        self.add_row("生成工具", producer)

    def values(self):
        return {
            "title": self.title_edit.text(),
            "author": self.author.text(),
            "subject": self.subject.text(),
            "keywords": self.keywords.text(),
        }


class RedactTextDialog(BaseDialog):
    def __init__(self, parent=None):
        BaseDialog.__init__(self, "按内容涂黑", parent, 460)
        self.text = self.add_row("要涂黑的文字", QtWidgets.QLineEdit())
        self.text.setPlaceholderText("例如：身份证号 / 手机号")
        self.mode = self.add_row("匹配方式", _combo([("纯文本", "text"), ("正则表达式", "regex")]))
        self.scope = self.add_row("范围", _combo([("全文", "all"), ("仅当前页", "current")]))
        self.add_hint("涂黑会真正删除底层的文字内容，无法通过复制还原。")

    def values(self):
        return {
            "text": self.text.text(),
            "mode": self.mode.currentData(),
            "scope": self.scope.currentData(),
        }


class AboutDialog(BaseDialog):
    def __init__(self, parent=None, qt_api="", mupdf_version=""):
        BaseDialog.__init__(self, "关于 %s" % APP_NAME, parent, 460)
        self.heading.setText(APP_NAME_CN)
        text = QtWidgets.QLabel(
            "<p style='line-height:1.7'>"
            "<b>%s %s</b><br>"
            "面向统信 UOS / 深度 Deepin 的轻量 PDF 编辑器。<br><br>"
            "渲染与编辑内核：PyMuPDF %s<br>"
            "界面框架：%s<br>"
            "授权协议：MIT"
            "</p>" % (APP_NAME, __version__, mupdf_version, qt_api)
        )
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        self.add_widget(text)
        self.buttons.setStandardButtons(QtWidgets.QDialogButtonBox.Ok)
        self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("关闭")


def _color_combo(items):
    box = QtWidgets.QComboBox()
    for label, rgb in items:
        pix = QtGui.QPixmap(16, 16)
        pix.fill(QtGui.QColor(int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)))
        painter = QtGui.QPainter(pix)
        painter.setPen(QtGui.QPen(QtGui.QColor("#c9ced8"), 1))
        painter.drawRect(0, 0, 15, 15)
        painter.end()
        box.addItem(QtGui.QIcon(pix), label, rgb)
    return box
