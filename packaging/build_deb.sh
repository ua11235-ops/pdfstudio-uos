#!/usr/bin/env bash
# 构建 deb 安装包（在 UOS / Debian 系系统上执行）
#
#   ./build_deb.sh
#
# 产物：build/pdfstudio_<版本>_all.deb
# 安装：sudo dpkg -i build/pdfstudio_1.0.0_all.deb
#       sudo apt -f install        # 若提示缺少依赖

set -e

APP_ID="pdfstudio"
APP_NAME="PDF 工作台"
VERSION="1.0.0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"
PKG_DIR="${BUILD_DIR}/${APP_ID}_${VERSION}_all"

if ! command -v dpkg-deb >/dev/null 2>&1; then
    echo "!! 没有找到 dpkg-deb，请在 Debian / UOS 系系统上执行本脚本"
    exit 1
fi

echo "==> 清理旧目录"
rm -rf "${PKG_DIR}"
mkdir -p "${PKG_DIR}/DEBIAN"
mkdir -p "${PKG_DIR}/opt/${APP_ID}"
mkdir -p "${PKG_DIR}/usr/bin"
mkdir -p "${PKG_DIR}/usr/share/applications"

echo "==> 复制程序文件"
cp -r "${SRC_DIR}/pdfstudio" "${PKG_DIR}/opt/${APP_ID}/"
cp "${SRC_DIR}/run.py" "${PKG_DIR}/opt/${APP_ID}/"
cp "${SRC_DIR}/README.md" "${PKG_DIR}/opt/${APP_ID}/" 2>/dev/null || true
find "${PKG_DIR}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "${PKG_DIR}" -name "*.pyc" -delete 2>/dev/null || true

cat > "${PKG_DIR}/usr/bin/${APP_ID}" <<EOF
#!/usr/bin/env bash
# 优先用装齐依赖的解释器：机器上可能同时有多个 python3，
# 依赖只装在其中某一个里面，用错了解释器就会 import 失败。
APP="/opt/${APP_ID}/run.py"

ready() {
    "\$1" -c 'import pymupdf' >/dev/null 2>&1 || "\$1" -c 'import fitz' >/dev/null 2>&1 || return 1
    "\$1" -c 'import PyQt5.QtWidgets' >/dev/null 2>&1 || "\$1" -c 'import PySide6.QtWidgets' >/dev/null 2>&1 || return 1
    return 0
}

if command -v python3 >/dev/null 2>&1 && ready python3; then
    exec python3 "\$APP" "\$@"
fi
for c in python3.13 python3.12 python3.11 python3.10 python3.9 python3.8 python3.7; do
    p="\$(command -v "\$c" 2>/dev/null)" || continue
    if ready "\$p"; then
        exec "\$p" "\$APP" "\$@"
    fi
done
# 都不完整时仍用 python3 启动，由 run.py 打印可操作的修复提示
exec python3 "\$APP" "\$@"
EOF
chmod 755 "${PKG_DIR}/usr/bin/${APP_ID}"

echo "==> 安装图标"
for size in 16 24 32 48 64 128 256 512; do
    src="${SCRIPT_DIR}/icons/${APP_ID}-${size}.png"
    [ -f "$src" ] || continue
    dir="${PKG_DIR}/usr/share/icons/hicolor/${size}x${size}/apps"
    mkdir -p "$dir"
    cp "$src" "${dir}/${APP_ID}.png"
done

cat > "${PKG_DIR}/usr/share/applications/${APP_ID}.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=PDF Studio
Name[zh_CN]=${APP_NAME}
GenericName=PDF Editor
GenericName[zh_CN]=PDF 编辑器
Comment=Read, annotate and edit PDF files
Comment[zh_CN]=轻量 PDF 阅读与编辑工具
Exec=/usr/bin/${APP_ID} %f
TryExec=/usr/bin/${APP_ID}
Icon=${APP_ID}
Terminal=false
Categories=Office;Graphics;Viewer;
MimeType=application/pdf;
Keywords=pdf;editor;annotate;ocr;
StartupNotify=true
StartupWMClass=pdfstudio
EOF

SIZE_KB="$(du -sk "${PKG_DIR}" | cut -f1)"

cat > "${PKG_DIR}/DEBIAN/control" <<EOF
Package: ${APP_ID}
Version: ${VERSION}
Section: office
Priority: optional
Architecture: all
Depends: python3 (>= 3.7), python3-pyqt5 | python3-pyside6, python3-fitz | python3-pymupdf
Recommends: python3-pip, tesseract-ocr, tesseract-ocr-chi-sim, fonts-noto-cjk
Installed-Size: ${SIZE_KB}
Maintainer: PDF Studio Project <pdfstudio@example.com>
Description: ${APP_NAME} - 轻量 PDF 阅读与编辑器
 一个用 Python + Qt + PyMuPDF 实现的 PDF 工具，支持阅读、批注、
 改字、页面插入删除旋转、水印页码、加密解密、涂黑脱敏、表单填写、
 拆分合并与导出。界面针对统信 UOS / 深度 Deepin 做了适配。
EOF

cat > "${PKG_DIR}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
EOF
chmod 755 "${PKG_DIR}/DEBIAN/postinst"

cat > "${PKG_DIR}/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
exit 0
EOF
chmod 755 "${PKG_DIR}/DEBIAN/prerm"

echo "==> 打包"
OUT="${BUILD_DIR}/${APP_ID}_${VERSION}_all.deb"
dpkg-deb --build --root-owner-group "${PKG_DIR}" "${OUT}" >/dev/null 2>&1 || \
    dpkg-deb --build "${PKG_DIR}" "${OUT}"

echo ""
echo "==> 构建完成：${OUT}"
echo "    安装：sudo dpkg -i ${OUT}"
echo "    修复依赖：sudo apt -f install"
