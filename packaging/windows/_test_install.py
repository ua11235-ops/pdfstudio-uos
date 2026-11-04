# -*- coding: utf-8 -*-
"""Windows 安装/卸载的端到端回归测试。

    python packaging/windows/_test_install.py

测的是**真正发出去的那个 zip**，不是源码目录：
解压 → 双击 安装.bat → 覆盖安装 → 运行自检 → 卸载 → 查注册表。

为什么要这么测：
    之前踩的坑全属于"脚本看着没错、跑起来就是不行"这一类。
    · .bat 用 LF 换行时 cmd 按错误偏移解析，setlocal 变成 etlocal；
    · 重复安装会把 .pdf 关联备份覆盖成自己的 ProgId，
      卸载后 .pdf 指向一个刚被删掉的 ProgId，双击 PDF 变成"没有关联"；
    · 源码目录里程序在 dist3/PDFStudio，压缩包里才是 PDFStudio/，
      在源码目录跑安装脚本必然报"找不到 PDFStudio.exe"——假失败。
    这些都得真解压、真装、真卸、真查注册表才看得见。

跑完会把 .pdf 关联还原成测试前的值，中途失败也会还原。
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

try:
    import winreg
except ImportError:
    sys.exit("这个测试只能在 Windows 上跑")

HERE = os.path.dirname(os.path.abspath(__file__))
ZIP = os.path.join(HERE, "build", u"PDF工作台-1.0.0-Windows.zip")

APP_NAME = u"PDF 工作台"
PROG_ID = "PDFStudio.Document"
# 模拟"机器上装了别的 PDF 阅读器"，用来做关联备份的基线
EXTERNAL_PROG_ID = "Contoso.PdfReader"
INSTALL_DIR = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "PDFStudio")
EXE = os.path.join(INSTALL_DIR, "PDFStudio.exe")

EXT_KEY = r"Software\Classes\.pdf"
OUR_PROG_KEY = r"Software\Classes" + "\\" + PROG_ID
BACKUP_KEY = r"Software\PDFStudio"
UNINST_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\PDFStudio"
# 哨兵子键：放在 .pdf 键里，用来验证安装脚本没有把整个 .pdf 键重建掉。
# New-Item -Force 在注册表上不是"已存在就跳过"，而是把键连同所有子键一起重建，
# 系统放在 .pdf 里的 OpenWithProgids 会被清空，用户以后就找不到"用别的程序打开"。
SENTINEL_KEY = r"Software\Classes\.pdf\OpenWithProgids"
SENTINEL_NAME = "PdfStudioSentinel"
START_LNK = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                         "Start Menu", "Programs", APP_NAME + ".lnk")
DESK_LNK = os.path.join(os.path.expanduser("~"), "Desktop", APP_NAME + ".lnk")

passed = []
failed = []


def check(name, ok, detail=""):
    if ok:
        passed.append(name)
        print("  OK   %s" % name)
    else:
        failed.append(name)
        print("  FAIL %s   %s" % (name, detail))


# ---------- 注册表 ----------

def read_default(path):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return winreg.QueryValueEx(key, "")[0]
    except OSError:
        return None


def read_prop(path, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def write_default(path, value):
    # SetValueEx 的签名是 (key, 值名, reserved, 类型, 数据)，5 个参数。
    # 少写一个 reserved 会直接抛 TypeError，结果就是"还原失败、关联被清空"。
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, value)


def key_exists(path):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path):
            return True
    except OSError:
        return False


def delete_tree(path):
    """递归删掉整个键。注册表没有"删不存在的键"的宽容写法，只能自己兜。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0,
                            winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    sub = winreg.EnumKey(key, 0)
                except OSError:
                    break
                delete_tree(path + "\\" + sub)
    except OSError:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except OSError:
        pass


# ---------- 跑脚本 ----------

def run_bat(folder, name, timeout=600, extra=None):
    """像用户双击一样跑 .bat。

    stdin 必须给 DEVNULL：.bat 结尾有 pause，等着按键。
    继承过来的 stdin 是个不会关闭的管道，pause 会一直卡住，
    表现成"测试跑了两分钟什么都没发生"。
    """
    argv = ["cmd", "/c", name] + list(extra or [])
    proc = subprocess.run(argv, cwd=folder, timeout=timeout,
                          stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def count_files(folder):
    total = 0
    for _root, _dirs, files in os.walk(folder):
        total += len(files)
    return total


# cmd 报"不认识这条命令"的几种写法。中文系统提示中文，但 chcp 65001 之后
# 系统消息会变成英文——只查中文那一条会漏掉一半。
STRAY = (u"不是内部或外部命令", "is not recognized",
         "not recognized as an internal", u"系统找不到指定的路径",
         "The system cannot find the path")


def no_stray(out):
    """输出里不该出现"某条命令不存在"这种噪声。"""
    for token in STRAY:
        if token in out:
            return False
    return True


def bad_rem_lines(folder):
    """找出 rem 行里混了中文的 .bat。

    cmd 在 chcp 65001 下解析含非 ASCII 的 rem 行会错位，
    把后半句当成命令执行，输出 "'文的参数错误，用户看不懂。' is not recognized"。
    中文放在 echo 里没问题，只有 rem 会中招，所以这条规则可以静态检查。
    """
    bad = []
    for name in (u"安装.bat", u"卸载.bat"):
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        with io.open(path, encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, 1):
                if line.strip().lower().startswith("rem") and \
                        any(ord(ch) > 127 for ch in line):
                    bad.append("%s:%d" % (name, lineno))
    return bad


def clean_slate():
    delete_tree(OUR_PROG_KEY)
    delete_tree(BACKUP_KEY)
    delete_tree(UNINST_KEY)
    for path in (START_LNK, DESK_LNK):
        if os.path.isfile(path):
            os.remove(path)
    if os.path.isdir(INSTALL_DIR):
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)


def seed_sentinel():
    """在 .pdf 键里放一个哨兵值，返回「是不是我们新建的」。

    只在不存在时创建，收尾时也只删我们自己建的那种，
    免得动到系统或用户原本就有的 OpenWithProgids。
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SENTINEL_KEY) as key:
            winreg.QueryValueEx(key, SENTINEL_NAME)
            return False
    except OSError:
        pass
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, SENTINEL_KEY) as key:
        winreg.SetValueEx(key, SENTINEL_NAME, 0, winreg.REG_SZ, "keep me")
    return True


def main():
    if not os.path.isfile(ZIP):
        sys.exit("找不到 %s\n请先跑：python packaging/windows/make_zip.py" % ZIP)

    work = tempfile.mkdtemp(prefix="pdfstudio_inst_")
    folder = None
    own_sentinel = False

    # machine_original 是这台机器上真实的值，收尾必须还原成它；
    # baseline 是这一轮测试"假装装之前就是这样"，断言都对着它。
    # 两者分开是因为机器可能停在上一轮测试的残留上（.pdf 指向本程序），
    # 那种状态下安装脚本按设计不会把自己的 ProgId 当原值备份，
    # 所有备份断言都会假失败——而真实用户不会遇到这种机器。
    machine_original = read_default(EXT_KEY)
    baseline = machine_original
    if baseline == PROG_ID:
        baseline = EXTERNAL_PROG_ID
        write_default(EXT_KEY, baseline)
        print("测试包：%s" % os.path.basename(ZIP))
        print("检测到上一轮残留（.pdf 仍指向本程序），测试基线改用 %s" % baseline)
        print("")
    else:
        print("测试包：%s" % os.path.basename(ZIP))
        print("测试前的 .pdf 关联：%s" % (baseline or "（无）"))
        print("")

    try:
        print("== 0. 解压压缩包 ==")
        with zipfile.ZipFile(ZIP) as zf:
            zf.extractall(work)
        names = os.listdir(work)
        folder = os.path.join(work, names[0])
        check("解压出唯一顶层目录", len(names) == 1, str(names))
        check("压缩包里有 安装.bat",
              os.path.isfile(os.path.join(folder, u"安装.bat")))
        check("压缩包里有 PDFStudio.exe",
              os.path.isfile(os.path.join(folder, "PDFStudio", "PDFStudio.exe")))
        bad = bad_rem_lines(folder)
        check(".bat 的 rem 行是纯 ASCII", not bad, "有中文注释：" + ", ".join(bad))

        print("")
        print("== 0b. 目录结构不标准时能不能自救 ==")
        # 用户报「找不到 PDFStudio.exe」时，真实原因几乎都是目录结构不对，
        # 而不是文件真丢了。这两种情况必须各自给出正确反应：
        #   A. 多套了一层目录 → 自动找到，别让人手工搬文件
        #   B. 程序真的不在 → 打印诊断，说清楚"大概率是没解压 / 被杀软删了"
        odd = os.path.join(work, "odd")
        os.makedirs(odd)
        for name in (u"安装.bat", u"卸载.bat", "install.ps1", "uninstall.ps1",
                     u"使用说明.txt"):
            shutil.copy2(os.path.join(folder, name), os.path.join(odd, name))

        # 用改名代替拷贝：同一块盘上是瞬时的，122MB 拷一遍太慢
        app_dir = os.path.join(folder, "PDFStudio")
        moved = os.path.join(odd, "inner", "PDFStudio")
        os.makedirs(os.path.join(odd, "inner"))
        os.rename(app_dir, moved)
        try:
            code, out = run_bat(odd, u"安装.bat", extra=["-DryRun"])
            check("多套一层目录时能自动找到程序",
                  code == 0 and u"已自动找到" in out, out[-800:])
            check("多套一层时输出干净", no_stray(out), out[-800:])
        finally:
            os.rename(moved, app_dir)

        # A2. 在源码目录里双击 安装.bat —— 程序在 dist3\PDFStudio，
        #     不认这个的话开发机上每次点都报"找不到 PDFStudio.exe"，
        #     看起来像打包坏了，其实是路径布局不同。
        dev = os.path.join(work, "dev")
        os.makedirs(os.path.join(dev, "dist3"))
        for name in (u"安装.bat", "install.ps1"):
            shutil.copy2(os.path.join(folder, name), os.path.join(dev, name))
        dev_app = os.path.join(dev, "dist3", "PDFStudio")
        os.rename(app_dir, dev_app)
        try:
            code, out = run_bat(dev, u"安装.bat", extra=["-DryRun"])
            check("源码目录里也能找到 dist3 的程序",
                  code == 0 and u"已自动找到" in out, out[-800:])
            check("提示这是开发构建目录", u"开发构建目录" in out, out[-800:])
            check("源码目录里输出干净", no_stray(out), out[-800:])
        finally:
            os.rename(dev_app, app_dir)

        # B1. 只解压出一个 .bat——"在压缩包里直接双击"就是这个样子
        lonely = os.path.join(work, "lonely")
        os.makedirs(lonely)
        shutil.copy2(os.path.join(folder, u"安装.bat"),
                     os.path.join(lonely, u"安装.bat"))

        code, out = run_bat(lonely, u"安装.bat")
        check("只解压出 .bat 时失败", code != 0, "退出码 %d" % code)
        check("提示缺少 install.ps1", u"缺少 install.ps1" in out, out[-600:])
        check("指出是在压缩包里双击了", u"直接在压缩包里双击" in out, out[-600:])
        check("没有把 PowerShell 英文报错甩给用户",
              "to the -File parameter does not exist" not in out, out[-600:])
        check("只解压出 .bat 时输出干净", no_stray(out), out[-600:])

        # B2. 脚本齐了但没有 PDFStudio 文件夹——用户这次遇到的就是这个
        noprog = os.path.join(work, "noprog")
        os.makedirs(noprog)
        for name in (u"安装.bat", "install.ps1"):
            shutil.copy2(os.path.join(folder, name), os.path.join(noprog, name))

        code, out = run_bat(noprog, u"安装.bat")
        check("缺程序时失败而不是假装成功", code != 0, "退出码 %d" % code)
        check("诊断指出没有 PDFStudio 文件夹",
              u"没有 PDFStudio 文件夹" in out, out[-900:])
        check("诊断指向「在压缩包里直接双击」这个原因",
              u"直接在压缩包里双击" in out, out[-900:])
        check("诊断给出 -AppDir 的用法", u"-AppDir" in out, out[-900:])
        check("诊断列出目录内容", u"共 2 项" in out and "install.ps1" in out,
              out[-900:])
        check("缺程序时输出干净", no_stray(out), out[-900:])

        print("")
        print("== 1. 从干净状态安装 ==")
        clean_slate()
        own_sentinel = seed_sentinel()
        code, out = run_bat(folder, u"安装.bat")
        check("安装.bat 正常退出", code == 0, "退出码 %d\n%s" % (code, out[-800:]))
        check("没有 cmd 解析错误", no_stray(out), out[:800])
        check("没有报找不到 exe", "找不到 PDFStudio.exe" not in out, out[:800])
        check("提示安装完成", u"安装完成" in out, out[-800:])
        check("程序已落地", os.path.isfile(EXE), EXE)
        check("文件数量对得上", count_files(INSTALL_DIR) > 50,
              "只拷了 %d 个文件" % count_files(INSTALL_DIR))
        check(".pdf 指向本程序", read_default(EXT_KEY) == PROG_ID,
              str(read_default(EXT_KEY)))
        check(".pdf 里原有的子键没被清掉",
              read_prop(SENTINEL_KEY, SENTINEL_NAME) == "keep me",
              "OpenWithProgids 被安装脚本重建掉了")
        check("备份记录了原关联",
              (read_prop(BACKUP_KEY, "PrevPdfProgId") or "") == (baseline or ""),
              "%r != %r" % (read_prop(BACKUP_KEY, "PrevPdfProgId"), baseline))
        check("开始菜单快捷方式", os.path.isfile(START_LNK))
        check("桌面快捷方式", os.path.isfile(DESK_LNK))
        check("已登记卸载入口",
              read_prop(UNINST_KEY, "UninstallString") is not None)

        print("")
        print("== 2. 覆盖安装（重复装一次）==")
        # 真正的回归点：第二次安装时 .pdf 已经是自己的 ProgId，
        # 如果备份被覆盖成自己的值，卸载就会把 .pdf 还原成一个刚被删掉的 ProgId。
        code, out = run_bat(folder, u"安装.bat")
        check("覆盖安装正常退出", code == 0, "退出码 %d" % code)
        check("覆盖安装没有 cmd 错误", no_stray(out), out[:800])
        check("覆盖安装没有残留旧文件", count_files(INSTALL_DIR) > 50,
              "%d 个文件" % count_files(INSTALL_DIR))
        check("备份没有被自己覆盖",
              (read_prop(BACKUP_KEY, "PrevPdfProgId") or "") == (baseline or ""),
              "备份变成了 %r，应该是 %r" % (
                  read_prop(BACKUP_KEY, "PrevPdfProgId"), baseline))

        print("")
        print("== 3. 装好的程序能跑 ==")
        shot = os.path.join(work, "selftest.png")
        proc = subprocess.run([EXE, "--selftest", shot], timeout=180,
                              stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        text = proc.stdout.decode("utf-8", "replace")
        check("自检通过", proc.returncode == 0 and "SELFTEST OK" in text,
              "退出码 %d\n%s" % (proc.returncode, text[-800:]))
        check("自检截图有内容",
              os.path.isfile(shot) and os.path.getsize(shot) > 20000)

        print("")
        print("== 4. 卸载 ==")
        code, out = run_bat(folder, u"卸载.bat")
        check("卸载.bat 正常退出", code == 0, "退出码 %d" % code)
        check("卸载没有 cmd 解析错误", no_stray(out), out[:800])
        check(".pdf 关联已还原",
              (read_default(EXT_KEY) or "") == (baseline or ""),
              "%r != %r" % (read_default(EXT_KEY), baseline))
        check("ProgId 已清理", not key_exists(OUR_PROG_KEY))
        check("备份键已清理", not key_exists(BACKUP_KEY))
        check("卸载登记已清理", not key_exists(UNINST_KEY))
        check("开始菜单快捷方式已删", not os.path.isfile(START_LNK))
        check("桌面快捷方式已删", not os.path.isfile(DESK_LNK))

        # 程序目录交给后台 cmd 删，等它跑完
        left = None
        for _ in range(40):
            left = count_files(INSTALL_DIR) if os.path.isdir(INSTALL_DIR) else 0
            if left == 0:
                break
            time.sleep(0.5)
        check("程序目录已清理", left == 0, "还剩 %d 个文件" % left)

    finally:
        print("")
        print("== 收尾：还原注册表、清临时目录 ==")
        try:
            clean_slate()
            if own_sentinel:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SENTINEL_KEY,
                                        0, winreg.KEY_ALL_ACCESS) as key:
                        winreg.DeleteValue(key, SENTINEL_NAME)
                except OSError:
                    pass
            if machine_original:
                write_default(EXT_KEY, machine_original)
            print("  .pdf 已还原为：%s" % (read_default(EXT_KEY) or "（无）"))
        except Exception as exc:
            print("  注册表还原失败，请手动处理：%s" % exc)
        shutil.rmtree(work, ignore_errors=True)

    print("")
    print("=" * 46)
    print("  通过 %d 项，失败 %d 项" % (len(passed), len(failed)))
    if failed:
        for name in failed:
            print("    · %s" % name)
        return 1
    print("  解压 / 安装 / 覆盖安装 / 运行 / 卸载 全部正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
