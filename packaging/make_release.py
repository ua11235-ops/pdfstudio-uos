# -*- coding: utf-8 -*-
"""打 UOS 源码发行包（tar.gz），产物可直接拷到 UOS 上解压安装。

    python packaging/make_release.py                  # 纯源码包（约 350K）
    python packaging/make_release.py --with-wheels    # 连离线依赖一起打（约 85MB）
    python packaging/make_release.py --verify         # 打完就地自检包内容

产物：packaging/build/pdfstudio-<版本>.tar.gz

为什么这段逻辑写在 Python 里、`make_release.sh` 只做转发：
    打包这台机器是 Windows，没有 bash，原来的 shell 脚本根本跑不起来。
    结果就是"发行包"变成了一个需要人肉记得去别的机器上重打的东西——
    实际交付的 79MB 包停在 10-28，连 10-29 加的「合并 PDF」都不在里面，
    而源码目录里测试全绿，谁也不会发现。脚本能在开发机上直接跑，
    "记得重新打包"这句话才成立。实现只留一份，两个入口不会各打各的包。
"""

import argparse
import os
import sys
import tarfile
import time

APP_ID = "pdfstudio"
VERSION = "1.0.0"
NAME = "%s-%s" % (APP_ID, VERSION)

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
BUILD_DIR = os.path.join(HERE, "build")
OUT = os.path.join(BUILD_DIR, NAME + ".tar.gz")

# 这些是本机开发/测试留下的，不该进发行包。
# 判断按"相对路径的目录段"做，不按字符串前缀，避免 ./sample 命中 ./samples。
SKIP_DIR_NAMES = {".git", ".venv", "venv", "__pycache__", ".idea", ".pytest_cache"}

# 相对路径前缀（用 / 分隔）
SKIP_PREFIXES = [
    "packaging/build",      # 上次打出来的包
    "samples/_out",         # 测试产物
    "screenshots/_test",    # 测试截图
]

# 开发机上的临时产物（自检截图等），不属于发行内容
SKIP_FILES = {"selftest.png"}

# PyInstaller 的中间目录：dist / dist2 / build8 ……
# 它们单个就上百 MB，混进"源码包"会让包体积翻十几倍，而且没人会去 UOS 上
# 解压一堆 Windows exe。按前缀匹配，新起的 dist9 也自动排除。
WINDOWS_BUILD_PREFIX = "packaging/windows/"


def _is_windows_build(rel):
    if not rel.startswith(WINDOWS_BUILD_PREFIX):
        return False
    rest = rel[len(WINDOWS_BUILD_PREFIX):]
    head = rest.split("/")[0]
    return head.startswith("dist") or head.startswith("build")


def should_skip(rel, with_wheels):
    """rel 是相对 SRC_DIR 的 posix 路径，判断是否排除。"""
    parts = rel.split("/")
    if any(p in SKIP_DIR_NAMES for p in parts):
        return True
    if rel.endswith(".pyc") or rel in SKIP_FILES:
        return True
    for prefix in SKIP_PREFIXES:
        if rel == prefix or rel.startswith(prefix + "/"):
            return True
    if _is_windows_build(rel):
        return True
    # 离线 wheel 体积大，默认不带，要带得显式说
    if not with_wheels and (rel == "packaging/wheels" or rel.startswith("packaging/wheels/")):
        return True
    return False


def collect(with_wheels):
    """返回 [(相对路径, 绝对路径)]，按路径排序保证两次打包顺序一致。"""
    items = []
    for folder, dirs, files in os.walk(SRC_DIR):
        dirs.sort()
        rel_dir = os.path.relpath(folder, SRC_DIR).replace(os.sep, "/")
        rel_dir = "" if rel_dir == "." else rel_dir

        # 整目录跳过时连目录本身都不写进包，省得包里留一堆空壳
        keep_dirs = []
        for name in dirs:
            rel = (rel_dir + "/" + name) if rel_dir else name
            if should_skip(rel, with_wheels):
                continue
            keep_dirs.append(name)
        dirs[:] = keep_dirs

        for fname in sorted(files):
            rel = (rel_dir + "/" + fname) if rel_dir else fname
            if should_skip(rel, with_wheels):
                continue
            items.append((rel, os.path.join(folder, fname)))
    return items


def _mode_for(rel):
    """补回可执行位。

    源码是在 Windows 上维护的，文件系统里没有 Unix 执行位；
    不显式写进 tar，UOS 上解包后 install.sh 就没有 +x，
    用户按文档敲 `sudo ./packaging/install.sh` 会得到 Permission denied。
    """
    if rel == "run.py":
        return 0o755
    if rel.startswith("packaging/") and rel.endswith(".sh"):
        return 0o755
    return 0o644


# 这些文件缺一个，装出来就是"能开但某个功能崩"，所以打完包必须核对一遍
REQUIRED = [
    "run.py", "README.md", "LICENSE", "requirements.txt", u"安装说明.md",
    "pdfstudio/__init__.py", "pdfstudio/app.py", "pdfstudio/qtcompat.py", "pdfstudio/__main__.py",
    "pdfstudio/core/document.py", "pdfstudio/core/pageops.py", "pdfstudio/core/merge.py",
    "pdfstudio/core/annotate.py", "pdfstudio/core/textops.py", "pdfstudio/core/security.py",
    "pdfstudio/core/decorate.py", "pdfstudio/core/export.py",
    "pdfstudio/ui/main_window.py", "pdfstudio/ui/page_view.py", "pdfstudio/ui/side_panel.py",
    "pdfstudio/ui/merge_dialog.py", "pdfstudio/ui/dialogs.py", "pdfstudio/ui/icons.py",
    "pdfstudio/ui/theme.py", "pdfstudio/ui/welcome.py", "pdfstudio/ui/find_bar.py",
    "packaging/install.sh", "packaging/build_deb.sh", "packaging/fetch_wheels.sh",
]

# 这些一旦出现在包里说明排除规则漏了。
# 不能只列 /dist8 这种具体名字：PyInstaller 下次失败会换 dist9、build9，
# 漏进去的是 100MB 的 Windows exe，而看条目数根本发现不了。
FORBIDDEN_HINTS = (
    "__pycache__", ".pyc", ".venv",
    "packaging/windows/dist", "packaging/windows/build",
)


def verify(out_path):
    """打完就地核对包内容，返回问题列表（空表示没问题）。"""
    problems = []
    with tarfile.open(out_path) as tar:
        names = [m.name for m in tar.getmembers()]
        files = set(n.split("/", 1)[1] for n in names if "/" in n)
        for rel in REQUIRED:
            if rel not in files:
                problems.append(u"缺少必需文件：%s" % rel)
        for name in names:
            low = name.lower()
            for hint in FORBIDDEN_HINTS:
                if hint in low:
                    problems.append(u"不该进包的东西：%s" % name)
                    break

        py_times = []
        for member in tar.getmembers():
            if member.name.endswith(".py"):
                py_times.append(member.mtime)
    if py_times:
        newest = time.strftime("%Y-%m-%d %H:%M", time.localtime(max(py_times)))
        print(u"    包内最新改动的 .py：%s" % newest)
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="make_release.py",
        description=u"打 UOS 源码发行包（tar.gz）")
    parser.add_argument("--with-wheels", action="store_true",
                        help=u"连 packaging/wheels 里的离线依赖一起打")
    # 核对默认开着：这次交付出问题的地方恰恰是"打了包但没人核过"，
    # 所以不能把它做成一个需要记得加的开关
    parser.add_argument("--verify", dest="verify", action="store_true", default=True,
                        help=u"打完就地核对包内容（默认开启）")
    parser.add_argument("--no-verify", dest="verify", action="store_false",
                        help=u"跳过包内容核对")
    args = parser.parse_args(argv)

    wheels = os.path.join(HERE, "wheels")
    if args.with_wheels and not os.path.isdir(wheels):
        sys.stderr.write(u"!! 没有找到 %s\n" % wheels)
        sys.stderr.write(u"   先跑一次：./fetch_wheels.sh --py 37\n")
        return 1

    # wheels 就在手边却没打进去，多半是忘了加参数。
    # UOS 的 apt 源封闭，没有这些 wheel 基本装不上依赖，
    # 打出来的包"能解压但装不了"，所以这里必须提醒。
    if not args.with_wheels and os.path.isdir(wheels):
        print(u"!! 注意：%s 里有离线依赖，但这次没有打进包" % wheels)
        print(u"!!       纯源码包在 UOS 上需要联网装 PyQt5，apt 源封闭时多半会失败")
        print(u"!!       要带上请加 --with-wheels")
        print("")

    if not os.path.isdir(BUILD_DIR):
        os.makedirs(BUILD_DIR)

    print(u"==> 收集文件")
    items = collect(args.with_wheels)
    if not items:
        sys.stderr.write(u"!! 没有收集到任何文件，检查 %s\n" % SRC_DIR)
        return 1

    print(u"==> 打包")
    # 先写临时文件再改名：中途失败不会留下一个"看起来能装"的半个包
    tmp_out = OUT + ".part"
    if os.path.exists(tmp_out):
        os.remove(tmp_out)
    with tarfile.open(tmp_out, "w:gz", compresslevel=9, format=tarfile.GNU_FORMAT) as tar:
        for rel, full in items:
            info = tar.gettarinfo(full, NAME + "/" + rel)
            info.mode = _mode_for(rel)
            # uid/gid 归零：源码里带着开发机的 197609，解包后在别人机器上
            # 看着像"外来用户的东西"，也不利于复现
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with open(full, "rb") as fh:
                tar.addfile(info, fh)
    os.replace(tmp_out, OUT)

    size_mb = os.path.getsize(OUT) / 1024.0 / 1024.0
    print("")
    print(u"    ✓ 生成：%s" % OUT)
    print(u"    ✓ %.1f MB，%d 个文件" % (size_mb, len(items)))

    has_wheels = any(r.startswith("packaging/wheels/") for r, _ in items)
    if has_wheels:
        count = sum(1 for r, _ in items if r.startswith("packaging/wheels/") and r.endswith(".whl"))
        print(u"    ✓ 已包含离线依赖（%d 个 wheel），UOS 上不需要 apt 也不需要联网" % count)
    else:
        print(u"    （纯源码包。UOS 装不上依赖时，改用 --with-wheels 重打）")

    print("")
    print(u"  拷到 UOS 后：")
    print(u"    tar -xzf %s.tar.gz" % NAME)
    print(u"    cd %s" % NAME)
    print(u"    sudo ./packaging/install.sh")
    print("")
    print(u"  只装给当前用户：")
    print(u"    ./packaging/install.sh --user")

    if args.verify:
        print("")
        print(u"==> 自检包内容")
        problems = verify(OUT)
        if problems:
            for item in problems:
                print(u"    !! %s" % item)
            return 1
        print(u"    ✓ 必需文件齐全，没有构建残留")
    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
