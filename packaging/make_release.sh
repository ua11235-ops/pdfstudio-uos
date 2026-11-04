#!/usr/bin/env bash
# 打源码发行包（tar.gz），产物可直接拷到 UOS 上解压安装。
#
#   ./make_release.sh                 # 纯源码包（小，约 350K）
#   ./make_release.sh --with-wheels   # 连离线依赖一起打（约 85MB）
#
# 产物：packaging/build/pdfstudio-<版本>.tar.gz
# 用法：tar -xzf pdfstudio-1.0.0.tar.gz && cd pdfstudio-1.0.0
#       sudo ./packaging/install.sh
#
# UOS 的 apt 源要激活才能用，装不上依赖时用 --with-wheels 最省事：
# 先 ./fetch_wheels.sh --py 37 下好 wheel，再打这个包。
#
# 真正的实现是 make_release.py：开发机是 Windows，没有 bash，
# shell 版本跑不起来就等于"发行包只能靠人记得去别处重打"，而这一步
# 恰恰是最容易漏的（漏了以后包比源码旧，本机测试还是全绿）。
# 这里只做转发，保证两个入口永远打同一个包。

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PY=""
for c in python3 python; do
    command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }
done
if [ -z "$PY" ]; then
    echo "!! 没有找到 python3，无法打包" >&2
    exit 1
fi

exec "$PY" "${SCRIPT_DIR}/make_release.py" "$@"
