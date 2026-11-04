# -*- coding: utf-8 -*-
"""统一 Windows 脚本的编码与换行，改完 .bat / .ps1 都要跑一次。

两条规则，方向相反，弄错任何一条都会出问题：

1. .bat 必须是 **CRLF + 无 BOM**
   - 只有 LF 时 cmd 会按错误偏移解析，setlocal 会变成 etlocal、echo. 变成 ho.
   - 有 BOM 时 cmd 会把 BOM 当成命令的一部分，报"不是内部或外部命令"

2. .ps1 必须是 **UTF-8 带 BOM**，换行用 CRLF
   - 没有 BOM 时 Windows 自带的 PS 5.1 会按本地 ANSI 解析，中文全变乱码

make_zip.py 会调用 main()，所以打包出来的一定是规范化过的；
不要指望"记得手动跑一遍"。
"""

import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BOM = b"\xef\xbb\xbf"


def _fix(name, want_bom):
    path = os.path.join(HERE, name)
    if not os.path.isfile(path):
        print("  跳过（不存在）: " + name)
        return
    raw = io.open(path, "rb").read()

    # 先统一去掉 BOM，最后按需要加回来
    if raw.startswith(BOM):
        raw = raw[3:]

    # 换行统一成 CRLF：先全部折成 LF，再把 LF 换成 CRLF，
    # 这样原本就是 CRLF 的不会变成 CRCRLF
    body = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    body = body.replace(b"\n", b"\r\n")

    if want_bom:
        body = BOM + body

    if body != io.open(path, "rb").read():
        io.open(path, "wb").write(body)
        print("  已修正: %s（%s，CRLF）" % (name, "带 BOM" if want_bom else "无 BOM"))
    else:
        print("  无需改动: %s" % name)


def main():
    print("== .bat：CRLF + 无 BOM ==")
    for name in (u"安装.bat", u"卸载.bat"):
        _fix(name, False)

    print("== .ps1：CRLF + 带 BOM ==")
    for name in ("install.ps1", "uninstall.ps1"):
        _fix(name, True)

    print("== .txt：CRLF（记事本友好）==")
    _fix(u"使用说明.txt", False)


if __name__ == "__main__":
    main()
