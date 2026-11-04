#!/usr/bin/env bash
# =============================================================================
# PDF 工作台 —— 一键安装脚本
# 适用：统信 UOS 20/23、深度 Deepin、麒麟 Kylin、Ubuntu 18.04+
#
#   sudo ./install.sh              安装到系统（所有用户可用）
#   ./install.sh --user            安装到当前用户（无需 root）
#   sudo ./install.sh --remove     卸载
#   ./install.sh --doctor          只诊断环境，不改动任何文件
#
# 选项：
#   -y, --yes       自动确认，不交互提问
#       --no-deps   跳过依赖自动安装，只做检查
#   -h, --help      显示本帮助
# =============================================================================

set -e

APP_ID="pdfstudio"
APP_NAME="PDF 工作台"
VERSION="1.0.0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 找不到依赖时依次尝试的解释器名（写进启动器做兜底）
FALLBACK_PYS="python3 python3.13 python3.12 python3.11 python3.10 python3.9 python3.8 python3.7 python"

# ------------------------------------------------------------------ 彩色输出
if [ -t 1 ] && command -v tput >/dev/null 2>&1 && [ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]; then
    C_RED="$(tput setaf 1)"; C_GRN="$(tput setaf 2)"; C_YEL="$(tput setaf 3)"
    C_DIM="$(tput setaf 8)"; C_OFF="$(tput sgr0)"
else
    C_RED=""; C_GRN=""; C_YEL=""; C_DIM=""; C_OFF=""
fi
info() { printf '==> %s\n' "$*"; }
ok()   { printf '    %s✓%s %s\n' "$C_GRN" "$C_OFF" "$*"; }
warn() { printf '%s!! %s%s\n' "$C_YEL" "$*" "$C_OFF"; }
fail() { printf '%s!! %s%s\n' "$C_RED" "$*" "$C_OFF" >&2; }
dim()  { printf '    %s%s%s\n' "$C_DIM" "$*" "$C_OFF"; }

usage() {
    cat <<TXT
用法：${0} [选项]

  --user          安装到当前用户（~/.local），不需要 root
  --remove        卸载（系统安装需 root）
  --doctor        只诊断运行环境并给出建议，不改动任何文件
  -y, --yes       自动确认，不交互提问
  --no-deps       跳过依赖自动安装，只做检查
  -h, --help      显示本帮助

示例：
  sudo ${0}        系统级安装（推荐，依赖会自动补齐）
  ${0} --user      只装给当前用户，不需要 root
  ${0} --doctor    启动不了时先跑这个

环境变量：
  PDFSTUDIO_PYTHON=/usr/bin/python3.7    强制指定用哪个解释器
TXT
}

# ------------------------------------------------------------------ 参数解析
MODE="system"      # 作用范围：system / user
ACTION="install"   # 动作：install / remove / doctor
ASSUME_YES=0
AUTO_DEPS=1

while [ $# -gt 0 ]; do
    case "$1" in
        --user)              MODE="user" ;;
        --system)            MODE="system" ;;
        --remove|--uninstall) ACTION="remove" ;;
        --doctor|--check|--diag) ACTION="doctor" ;;
        -y|--yes)            ASSUME_YES=1 ;;
        --no-deps)           AUTO_DEPS=0 ;;
        -h|--help)           usage; exit 0 ;;
        *) fail "未知参数：$1"; echo; usage; exit 2 ;;
    esac
    shift
done

if [ "$MODE" = "user" ]; then
    PREFIX="${HOME}/.local/share/${APP_ID}"
    BIN_DIR="${HOME}/.local/bin"
    DESKTOP_DIR="${HOME}/.local/share/applications"
    ICON_ROOT="${HOME}/.local/share/icons/hicolor"
else
    PREFIX="/opt/${APP_ID}"
    BIN_DIR="/usr/local/bin"
    DESKTOP_DIR="/usr/share/applications"
    ICON_ROOT="/usr/share/icons/hicolor"
fi

# =============================================================================
#  环境探测工具函数
# =============================================================================

py3_ok() { "$1" -c 'import sys;raise SystemExit(0 if sys.version_info[0]==3 else 1)' >/dev/null 2>&1; }

py_ver() { "$1" -c 'import sys;print("%d.%d.%d"%sys.version_info[:3])' 2>/dev/null || echo "?"; }
py_minor() { "$1" -c 'import sys;print(sys.version_info[1])' 2>/dev/null || echo "0"; }

# PyMuPDF 新旧两种导入名都认：1.24 起推荐 pymupdf，之前只有 fitz
has_pdf() { "$1" -c 'import pymupdf' >/dev/null 2>&1 || "$1" -c 'import fitz' >/dev/null 2>&1; }

pdf_ver() {
    "$1" -c '
import sys
try:
    import pymupdf as m
except Exception:
    try:
        import fitz as m
    except Exception:
        print("-"); sys.exit(0)
v = getattr(m, "__version__", None) or getattr(m, "VersionBind", None)
if not v:
    try:
        v = ".".join(str(x) for x in m.version[:3])
    except Exception:
        v = "-"
print(v)
' 2>/dev/null || echo "-"
}

# QtSvg / QtPrintSupport 是本程序硬依赖（图标与打印），必须一起检查
has_qt() {
    "$1" -c 'import PyQt5.QtWidgets, PyQt5.QtSvg, PyQt5.QtPrintSupport' >/dev/null 2>&1 && return 0
    "$1" -c 'import PySide6.QtWidgets, PySide6.QtSvg, PySide6.QtPrintSupport' >/dev/null 2>&1 && return 0
    return 1
}

qt_name() {
    if "$1" -c 'import PyQt5.QtWidgets' >/dev/null 2>&1; then
        echo "PyQt5"
    elif "$1" -c 'import PySide6.QtWidgets' >/dev/null 2>&1; then
        echo "PySide6"
    else
        echo "-"
    fi
}

PY_LIST_CACHE=""

# 解释器自身路径。这里刻意不用 realpath：
# 虚拟环境里的 bin/python 是指向系统解释器的符号链接，realpath 会把 venv 抹掉，
# 导致 venv 里装好的依赖被误判为"缺失"。
py_exe() {
    "$1" -c 'import os,sys
p = sys.executable or ""
print(os.path.abspath(p) if p else "")' 2>/dev/null || true
}

# 输出所有可用的 python3 解释器绝对路径，高版本在前，已去重
# 注意必须以换行结尾：while read 会丢弃没有换行符的最后一行
find_pythons() {
    if [ -n "$PY_LIST_CACHE" ]; then
        printf '%s\n' "$PY_LIST_CACHE"
        return 0
    fi
    local out="" c raw real
    for c in python3.13 python3.12 python3.11 python3.10 python3.9 python3.8 python3.7 python3 python; do
        raw="$(command -v "$c" 2>/dev/null || true)"
        [ -n "$raw" ] || continue
        real="$(py_exe "$raw")"
        [ -n "$real" ] || real="$(readlink -f "$raw" 2>/dev/null || printf '%s' "$raw")"
        [ -x "$real" ] || continue
        py3_ok "$real" || continue
        # python 与 python3 常指向同一个二进制，按路径去重
        case "
${out}
" in
            *"
${real}
"*) continue ;;
        esac
        out="${out}${out:+
}${real}"
    done
    PY_LIST_CACHE="${out}"
    printf '%s\n' "$PY_LIST_CACHE"
}

# 已经装齐依赖的解释器（最优解，什么都不用装）
pick_ready() {
    local p
    while IFS= read -r p; do
        [ -n "$p" ] || continue
        if has_pdf "$p" && has_qt "$p"; then
            printf '%s' "$p"
            return 0
        fi
    done < <(find_pythons)
    return 1
}

# 退而求其次：挑一个"最接近可用"的解释器作为安装目标
# 评分：已有依赖权重最高，其次版本号
pick_target() {
    local p best="" bestscore=-1 score m
    while IFS= read -r p; do
        [ -n "$p" ] || continue
        score=0
        has_pdf "$p" && score=$((score + 100))
        has_qt  "$p" && score=$((score + 100))
        m="$(py_minor "$p")"
        score=$((score + m))
        if [ "$score" -gt "$bestscore" ]; then
            bestscore="$score"
            best="$p"
        fi
    done < <(find_pythons)
    printf '%s' "$best"
}

# 按 Python 版本挑能装上的 PyMuPDF：新版轮子已经不支持 3.7/3.8
pdf_spec() {
    local m
    m="$(py_minor "$1")"
    if [ "$m" -le 7 ] 2>/dev/null; then
        echo "pymupdf<=1.22.5"
    elif [ "$m" -eq 8 ] 2>/dev/null; then
        echo "pymupdf<=1.23.26"
    else
        echo "pymupdf"
    fi
}

can_root() {
    [ "$(id -u)" -eq 0 ] && return 0
    command -v sudo >/dev/null 2>&1 && return 0
    return 1
}

# ------------------------------------------------------------ 依赖安装辅助

# 判断是不是统信 UOS / 深度 Deepin 系
is_uos() {
    [ -f /etc/os-release ] || return 1
    grep -qiE "uos|uniontech|deepin" /etc/os-release 2>/dev/null
}

# UOS 没开开发者模式时，sudo 装包会被安全策略拦下来
uos_devmode_on() {
    [ -e /etc/uos-developer-mode ] || [ -e /var/lib/deepin/developer_mode ]
}

# pip 源。UOS 的 apt 源要激活才能用，但 pip 走国内镜像是通的，
# 所以 pip 才是 UOS 上真正靠得住的安装途径。
pip_index() {
    if [ -n "${PDFSTUDIO_PIP_INDEX:-}" ]; then
        printf '%s' "$PDFSTUDIO_PIP_INDEX"
    elif [ -n "${PIP_INDEX_URL:-}" ]; then
        printf '%s' "$PIP_INDEX_URL"
    else
        printf '%s' "https://pypi.tuna.tsinghua.edu.cn/simple"
    fi
}

# 本地 wheel 目录：有就离线装，完全绕开 apt 和网络
find_wheels_dir() {
    local d
    for d in "${SCRIPT_DIR}/wheels" "${SRC_DIR}/packaging/wheels" "${PREFIX}/wheels"; do
        [ -d "$d" ] || continue
        ls "$d"/*.whl >/dev/null 2>&1 || continue
        printf '%s' "$d"
        return 0
    done
    return 1
}

# pip 输出必须可见。以前全部丢进 /dev/null，下载 60MB 时用户看到的
# 就是"卡住"，实际只是慢。现在原样透出，只是缩进一下。
pip_run() {
    (
        set +e
        "$1" -m pip install "${@:2}" 2>&1 | sed -u 's/^/      /'
        exit "${PIPESTATUS[0]}"
    )
}

# 确保 pip 可用。UOS 上 python3-pip 本身也要 apt 装，
# 源不通时就只能靠 Python 自带的 ensurepip 或官方 get-pip.py。
ensure_pip() {
    local py="$1" m tmp
    "$py" -m pip --version >/dev/null 2>&1 && return 0

    dim "该解释器没有 pip，尝试补装"
    if "$py" -m ensurepip --upgrade >/dev/null 2>&1 && \
       "$py" -m pip --version >/dev/null 2>&1; then
        return 0
    fi

    # Debian 系会把 ensurepip 剥掉，退而求其次拿官方 get-pip.py
    m="$(py_minor "$py")"
    tmp="/tmp/get-pip.$$.py"
    if command -v curl >/dev/null 2>&1; then
        if [ "$m" -le 7 ] 2>/dev/null; then
            curl -fsSL --connect-timeout 20 -o "$tmp" https://bootstrap.pypa.io/pip/3.7/get-pip.py 2>/dev/null || true
        else
            curl -fsSL --connect-timeout 20 -o "$tmp" https://bootstrap.pypa.io/get-pip.py 2>/dev/null || true
        fi
    elif command -v wget >/dev/null 2>&1; then
        if [ "$m" -le 7 ] 2>/dev/null; then
            wget -q -T 20 -O "$tmp" https://bootstrap.pypa.io/pip/3.7/get-pip.py 2>/dev/null || true
        else
            wget -q -T 20 -O "$tmp" https://bootstrap.pypa.io/get-pip.py 2>/dev/null || true
        fi
    fi
    if [ -s "$tmp" ]; then
        "$py" "$tmp" --no-warn-script-location >/dev/null 2>&1 || true
        rm -f "$tmp"
    fi

    "$py" -m pip --version >/dev/null 2>&1
}

run_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        return 127
    fi
}

# =============================================================================
#  诊断模式：只读，不改动任何文件
# =============================================================================
if [ "$ACTION" = "doctor" ]; then
    echo
    info "系统信息"
    dim "程序版本：${APP_NAME} ${VERSION}"
    if [ -f /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release 2>/dev/null || true
        dim "发行版：${PRETTY_NAME:-未知}"
    fi
    dim "内核：$(uname -srm 2>/dev/null || echo '未知')"
    dim "桌面会话：${XDG_SESSION_TYPE:-未知}  DISPLAY=${DISPLAY:-未设置}"
    dim "当前用户：$(id -un)  (uid=$(id -u))"
    if is_uos; then
        dim "系统类型：统信 UOS / Deepin 系"
        if uos_devmode_on; then
            dim "开发者模式：已开启"
        else
            dim "开发者模式：未开启（sudo 装包可能被拦，控制中心 → 通用 → 开发者模式）"
        fi
    fi

    echo
    info "Python 解释器"
    found_any=0
    while IFS= read -r p; do
        [ -n "$p" ] || continue
        found_any=1
        pdf_s="$(has_pdf "$p" && pdf_ver "$p" || echo '缺失')"
        qt_s="$(qt_name "$p")"
        pip_s="$("$p" -m pip --version 2>/dev/null | cut -d' ' -f2 || true)"
        printf '    %s\n' "$p"
        printf '        版本 %-8s  PyMuPDF: %-12s Qt: %-8s pip: %s\n' \
            "$(py_ver "$p")" "$pdf_s" "$qt_s" "${pip_s:-无}"
    done < <(find_pythons)
    if [ "$found_any" -eq 0 ]; then
        warn "没有找到任何 python3 解释器"
    fi

    echo
    info "依赖来源"
    if WHEELS_SHOW="$(find_wheels_dir)"; then
        ok "本地 wheel 目录：${WHEELS_SHOW}"
        dim "安装时会优先离线安装，不需要 apt，也不需要联网"
    else
        dim "没有本地 wheel 目录"
        dim "UOS 上 apt 装不上时，用 ./fetch_wheels.sh --py 37 下一份拷过来"
    fi
    dim "pip 源：$(pip_index)"

    echo
    info "结论"
    if READY="$(pick_ready)"; then
        ok "环境已就绪，可直接运行：${READY} run.py"
        dim "若桌面图标点不开，说明安装时的解释器与现在不同，重跑 sudo ${0} 即可"
    else
        warn "依赖不完整，运行 sudo ${0} 会自动补齐"
        dim "PyMuPDF（PDF 内核）+ PyQt5 或 PySide6（界面），两者都需要"
        if is_uos; then
            dim "UOS 的 apt 源要激活才能用，脚本会绕开 apt 走 pip 或离线 wheel"
        fi
    fi
    echo
    exit 0
fi

# =============================================================================
#  卸载
# =============================================================================
if [ "$ACTION" = "remove" ]; then
    if [ "$MODE" = "system" ] && [ "$(id -u)" -ne 0 ]; then
        fail "卸载系统安装需要 root 权限，请执行：sudo ./install.sh --remove"
        fail "如果当初是用 --user 装的，请执行：./install.sh --user --remove"
        exit 1
    fi
    info "正在卸载 ${APP_NAME}"
    rm -rf "${PREFIX}"
    rm -f "${BIN_DIR}/${APP_ID}"
    rm -f "${DESKTOP_DIR}/${APP_ID}.desktop"
    for size in 16 24 32 48 64 128 256 512; do
        rm -f "${ICON_ROOT}/${size}x${size}/apps/${APP_ID}.png"
    done
    command -v update-desktop-database >/dev/null 2>&1 && \
        update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || true
    ok "已卸载"
    exit 0
fi

# =============================================================================
#  安装
# =============================================================================
if [ "$MODE" = "system" ] && [ "$(id -u)" -ne 0 ]; then
    fail "安装到系统目录需要 root 权限，请执行：sudo ./install.sh"
    dim "或者安装到当前用户：./install.sh --user"
    exit 1
fi

# ---------------------------------------------------------------- 1. 复制程序
info "安装到 ${PREFIX}"
mkdir -p "${PREFIX}"
# 只清程序本体，保留已有 venv，重装时不必重新下载依赖
rm -rf "${PREFIX}/pdfstudio"
cp -r "${SRC_DIR}/pdfstudio" "${PREFIX}/"
cp "${SRC_DIR}/run.py" "${PREFIX}/"
cp "${SRC_DIR}/README.md" "${PREFIX}/" 2>/dev/null || true
find "${PREFIX}/pdfstudio" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
ok "程序文件已复制"

# ---------------------------------------------------------------- 2. 依赖处理
info "检查运行依赖"

# 允许强制指定解释器，绕过自动探测：
#   PDFSTUDIO_PYTHON=/usr/bin/python3.7 sudo ./install.sh
# 机器上装了多个 Python、或自动探测挑错了的时候用这个
if [ -n "${PDFSTUDIO_PYTHON:-}" ]; then
    if [ -x "$PDFSTUDIO_PYTHON" ] && py3_ok "$PDFSTUDIO_PYTHON"; then
        PY_LIST_CACHE="$PDFSTUDIO_PYTHON"
        dim "已按 PDFSTUDIO_PYTHON 指定解释器"
    else
        fail "PDFSTUDIO_PYTHON 指向的不是可用的 Python 3：$PDFSTUDIO_PYTHON"
        rm -rf "${PREFIX}"
        exit 1
    fi
fi

RUN_PY=""
NEED_PDF=0
NEED_QT=0

if RUN_PY="$(pick_ready)"; then
    ok "Python: ${RUN_PY}  ($(py_ver "$RUN_PY"))"
    ok "PyMuPDF: $(pdf_ver "$RUN_PY")"
    ok "Qt: $(qt_name "$RUN_PY")"
else
    TARGET="$(pick_target)"
    if [ -z "$TARGET" ]; then
        fail "没有找到任何 python3 解释器"
        dim "请先安装：sudo apt install python3"
        rm -rf "${PREFIX}"
        exit 1
    fi
    warn "解释器 ${TARGET} 依赖不完整，准备补齐"
    has_pdf "$TARGET" || NEED_PDF=1
    has_qt  "$TARGET" || NEED_QT=1

    if [ "$AUTO_DEPS" -eq 0 ]; then
        fail "--no-deps 已指定，跳过自动安装"
        rm -rf "${PREFIX}"
        exit 1
    fi

    # 要动系统包了，先问一声；加 -y 或非交互执行时直接继续
    if [ "$ASSUME_YES" -eq 0 ] && [ -t 0 ]; then
        printf '    将自动安装缺失的依赖（会用到 apt / pip），继续？[Y/n] '
        read -r ANSWER || ANSWER="y"
        case "$ANSWER" in
            [nN]*)
                fail "已取消。依赖需要手动安装后再运行本脚本"
                dim "排查命令：./install.sh --doctor"
                rm -rf "${PREFIX}"
                exit 1
                ;;
        esac
    fi

    # --- 方案 0：本地 wheel 目录（离线安装，最快最稳） ---
    # UOS 的 apt 源要激活、要开发者模式，很多时候根本装不上；
    # 把 wheel 提前下好拷过来，pip 直接离线装，什么都不用管。
    if [ -z "$RUN_PY" ] && WHEELS="$(find_wheels_dir)"; then
        if ensure_pip "$TARGET"; then
            PKGS=""
            has_qt  "$TARGET" || PKGS="${PKGS} PyQt5"
            has_pdf "$TARGET" || PKGS="${PKGS} pymupdf"
            if [ -n "$PKGS" ]; then
                info "发现离线 wheel 目录，本地安装：${WHEELS}"
                USER_ARG=""
                [ "$(id -u)" -ne 0 ] && USER_ARG="--user"
                if ! pip_run "$TARGET" --no-index --find-links "$WHEELS" ${USER_ARG} ${PKGS}; then
                    # UOS 20 自带的 pip 可能低于 19.0，认不出 manylinux2014 标签，
                    # 会直接拒绝 wheel。升一级 pip 通常就好了。
                    dim "离线安装没成功，可能是 pip 太旧，升级后重试"
                    "$TARGET" -m pip install --upgrade pip -i "$(pip_index)" >/dev/null 2>&1 || true
                    pip_run "$TARGET" --no-index --find-links "$WHEELS" ${USER_ARG} ${PKGS} || true
                fi
            fi
            if READY0="$(pick_ready)"; then
                RUN_PY="$READY0"
                ok "Python: ${RUN_PY}  ($(py_ver "$RUN_PY"))"
                ok "PyMuPDF: $(pdf_ver "$RUN_PY")"
                ok "Qt: $(qt_name "$RUN_PY")"
            fi
        fi
    fi

    # --- 方案 A：apt 装系统包（源可用时才走得通） ---
    if [ -z "$RUN_PY" ] && can_root && command -v apt-get >/dev/null 2>&1; then
        PKGS=""
        [ "$NEED_QT" -eq 1 ] && PKGS="${PKGS} python3-pyqt5"
        [ "$NEED_PDF" -eq 1 ] && PKGS="${PKGS} python3-pymupdf"
        info "尝试用 apt 安装：${PKGS# }"
        APT_DONE=0
        if run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ${PKGS} >/dev/null 2>&1; then
            APT_DONE=1
        else
            # python3-pymupdf 只有较新的发行版才有，老系统叫 python3-fitz
            if [ "$NEED_PDF" -eq 1 ]; then
                run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3-fitz >/dev/null 2>&1 && APT_DONE=1
            fi
            # 包索引可能过期，更新后再试一次
            if [ "$APT_DONE" -eq 0 ]; then
                run_root env DEBIAN_FRONTEND=noninteractive apt-get update >/dev/null 2>&1 || true
                run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ${PKGS} >/dev/null 2>&1 && APT_DONE=1
                if [ "$APT_DONE" -eq 0 ] && [ "$NEED_PDF" -eq 1 ]; then
                    run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3-fitz >/dev/null 2>&1 && APT_DONE=1
                fi
            fi
        fi
        if [ "$APT_DONE" -eq 1 ]; then
            ok "apt 安装完成"
        else
            # UOS 上 apt 失败几乎都是源不可用，把原因说清楚，别让用户瞎试
            if is_uos; then
                warn "apt 装不上。UOS 的软件源要系统已激活才可用"
                if ! uos_devmode_on; then
                    dim "另外开发者模式似乎没开：控制中心 → 通用 → 开发者模式 → 进入开发者模式"
                fi
                dim "下面改用 pip + 国内镜像，这条路不依赖 UOS 源"
            else
                dim "apt 没有可用的包，改用 pip"
            fi
        fi
        if READY2="$(pick_ready)"; then
            RUN_PY="$READY2"
            ok "Python: ${RUN_PY}  ($(py_ver "$RUN_PY"))"
            ok "PyMuPDF: $(pdf_ver "$RUN_PY")"
            ok "Qt: $(qt_name "$RUN_PY")"
        fi
    fi

    # --- 方案 B：pip 装进目标解释器（UOS 上的主力方案） ---
    if [ -z "$RUN_PY" ]; then
        has_pdf "$TARGET" || NEED_PDF=1
        has_qt  "$TARGET" || NEED_QT=1
        SPEC="$(pdf_spec "$TARGET")"
        IDX="$(pip_index)"

        # 非 root 装到用户目录；root 直接装系统，遇到 PEP 668 再退一步
        PIP_ARGS=""
        [ "$(id -u)" -ne 0 ] && PIP_ARGS="--user"

        if ensure_pip "$TARGET"; then
            # 超时和重试都设上，网络差时不至于无限挂着
            PIP_OPTS="--timeout 60 --retries 3 -i ${IDX}"

            if [ "$NEED_QT" -eq 1 ]; then
                info "pip 安装 PyQt5（约 70MB，下面有下载进度，不是卡死）"
                dim "源：${IDX}"
                pip_run "$TARGET" ${PIP_OPTS} ${PIP_ARGS} PyQt5 || \
                    pip_run "$TARGET" ${PIP_OPTS} ${PIP_ARGS} --break-system-packages PyQt5 || \
                    warn "PyQt5 安装失败"
            fi
            if [ "$NEED_PDF" -eq 1 ]; then
                info "pip 安装 ${SPEC}"
                pip_run "$TARGET" ${PIP_OPTS} ${PIP_ARGS} "${SPEC}" || \
                    pip_run "$TARGET" ${PIP_OPTS} ${PIP_ARGS} --break-system-packages "${SPEC}" || \
                    warn "PyMuPDF 安装失败"
            fi
        else
            warn "拿不到 pip，稍后尝试用虚拟环境"
        fi

        if READY3="$(pick_ready)"; then
            RUN_PY="$READY3"
            ok "Python: ${RUN_PY}  ($(py_ver "$RUN_PY"))"
            ok "PyMuPDF: $(pdf_ver "$RUN_PY")"
            ok "Qt: $(qt_name "$RUN_PY")"
        fi
    fi

    # --- 方案 C：venv 兜底 ---
    # 系统 Python 被 PEP 668 锁住、或 apt 与 pip 都装不上时，用独立虚拟环境
    if [ -z "$RUN_PY" ]; then
        info "尝试创建独立运行环境 ${PREFIX}/venv"
        VENV_PY="${PREFIX}/venv/bin/python"
        if [ ! -x "$VENV_PY" ]; then
            rm -rf "${PREFIX}/venv"
            if ! "$TARGET" -m venv --system-site-packages "${PREFIX}/venv" >/dev/null 2>&1; then
                if can_root && command -v apt-get >/dev/null 2>&1; then
                    run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3-venv >/dev/null 2>&1 || true
                fi
                "$TARGET" -m venv --system-site-packages "${PREFIX}/venv" >/dev/null 2>&1 || true
            fi
        fi
        if [ -x "$VENV_PY" ]; then
            SPEC="$(pdf_spec "$VENV_PY")"
            IDX="$(pip_index)"
            VENV_OPTS="--timeout 60 --retries 3"
            # 有本地 wheel 就离线装，没有才联网
            if WHEELS2="$(find_wheels_dir)"; then
                VENV_OPTS="${VENV_OPTS} --no-index --find-links ${WHEELS2}"
            else
                VENV_OPTS="${VENV_OPTS} -i ${IDX}"
            fi
            has_qt  "$VENV_PY" || pip_run "$VENV_PY" ${VENV_OPTS} PyQt5 >/dev/null 2>&1 || true
            has_pdf "$VENV_PY" || pip_run "$VENV_PY" ${VENV_OPTS} "${SPEC}" >/dev/null 2>&1 || true
            if has_pdf "$VENV_PY" && has_qt "$VENV_PY"; then
                RUN_PY="$VENV_PY"
                ok "独立环境可用：${VENV_PY}"
            fi
        fi
    fi

    # --- 全部失败：给出可复制的命令 ---
    if [ -z "$RUN_PY" ]; then
        echo
        fail "依赖自动安装失败"
        echo
        if is_uos; then
            echo "  UOS 的 apt 源需要系统激活才能用，装不上是正常的。推荐走离线方式："
            echo
            echo "  ${C_DIM}# 1. 在任意一台有网的电脑上（Windows/macOS/Linux 都行）${C_OFF}"
            echo "     ./packaging/fetch_wheels.sh --py 37"
            echo "     把生成的 packaging/wheels/ 整个目录拷到这台机器"
            echo
            echo "  ${C_DIM}# 2. 在本机执行（假设 wheels 放在当前目录下）${C_OFF}"
            echo "     ${TARGET} -m pip install --no-index --find-links wheels PyQt5 pymupdf"
            echo
            echo "  ${C_DIM}# 3. 重新运行安装脚本${C_OFF}"
            echo "     sudo ${0}"
            echo
            echo "  ${C_DIM}# 或者直接用 pip 走国内镜像（需要本机能访问外网）${C_OFF}"
            echo "     ${TARGET} -m pip install -i $(pip_index) PyQt5 $(pdf_spec "$TARGET")"
        else
            echo "  请手动执行下面任意一组命令，然后重新运行本脚本："
            echo
            echo "  ${C_DIM}# 用 apt（Debian / Ubuntu）${C_OFF}"
            echo "    sudo apt install python3-pyqt5 python3-pymupdf"
            echo "    sudo apt install python3-pyqt5 python3-fitz        # 老系统包名"
            echo
            echo "  ${C_DIM}# 用 pip 装到刚才选中的解释器（关键是别装到别的 python 里）${C_OFF}"
            echo "    ${TARGET} -m pip install -i $(pip_index) PyQt5 $(pdf_spec "$TARGET")"
            echo
            echo "  ${C_DIM}# 系统 Python 被锁定（externally-managed-environment）时${C_OFF}"
            echo "    ${TARGET} -m pip install --break-system-packages -i $(pip_index) PyQt5 pymupdf"
        fi
        echo
        echo "  ${C_DIM}# 没网也行：在别的机器上 ./packaging/fetch_wheels.sh --py 37，${C_OFF}"
        echo "  ${C_DIM}# 把 wheels 目录拷过来，重跑本脚本即可离线安装${C_OFF}"
        echo
        dim "排查命令：${0} --doctor"
        rm -rf "${PREFIX}"
        exit 1
    fi
fi

# ---------------------------------------------------------------- 3. 启动器
# 把探测到的解释器绝对路径写死，避免运行时 PATH 指向别的 python
mkdir -p "${BIN_DIR}"
cat > "${BIN_DIR}/${APP_ID}" <<EOF
#!/usr/bin/env bash
# 由 install.sh 生成：安装时探测到的解释器是 ${RUN_PY}
# 如果该解释器被删掉，会退回到 PATH 里的 python3
PY="${RUN_PY}"
if [ ! -x "\$PY" ]; then
    for c in ${FALLBACK_PYS}; do
        if command -v "\$c" >/dev/null 2>&1; then
            PY="\$(command -v "\$c")"
            break
        fi
    done
fi
exec "\$PY" "${PREFIX}/run.py" "\$@"
EOF
chmod +x "${BIN_DIR}/${APP_ID}"
ok "启动器：${BIN_DIR}/${APP_ID}"

# ---------------------------------------------------------------- 4. 图标
for size in 16 24 32 48 64 128 256 512; do
    src="${SCRIPT_DIR}/icons/${APP_ID}-${size}.png"
    [ -f "$src" ] || continue
    mkdir -p "${ICON_ROOT}/${size}x${size}/apps"
    cp "$src" "${ICON_ROOT}/${size}x${size}/apps/${APP_ID}.png"
done

# ---------------------------------------------------------------- 5. 桌面入口
mkdir -p "${DESKTOP_DIR}"
cat > "${DESKTOP_DIR}/${APP_ID}.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=PDF Studio
Name[zh_CN]=${APP_NAME}
GenericName=PDF Editor
GenericName[zh_CN]=PDF 编辑器
Comment=Read, annotate and edit PDF files
Comment[zh_CN]=轻量 PDF 阅读与编辑工具
Exec=${BIN_DIR}/${APP_ID} %f
TryExec=${BIN_DIR}/${APP_ID}
Icon=${APP_ID}
Terminal=false
Categories=Office;Graphics;Viewer;
MimeType=application/pdf;
Keywords=pdf;editor;annotate;ocr;
StartupNotify=true
StartupWMClass=pdfstudio
EOF
chmod 644 "${DESKTOP_DIR}/${APP_ID}.desktop"

command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -f -t "${ICON_ROOT}" 2>/dev/null || true

# ---------------------------------------------------------------- 6. 自检
info "自检"
"$RUN_PY" -c "import sys; sys.path.insert(0, '${PREFIX}'); import pdfstudio" >/dev/null 2>&1 \
    && ok "程序模块可导入" \
    || warn "程序模块导入异常，请运行：${APP_ID} 查看报错"

echo
info "安装完成 ${APP_NAME} ${VERSION}"
echo "    解释器：${RUN_PY}  ($(py_ver "$RUN_PY"))"
echo "    启动方式：启动器搜索「${APP_NAME}」，或终端执行 ${APP_ID}"
if [ "$MODE" = "user" ]; then
    echo "    提示：${BIN_DIR} 需加入 PATH 才能在终端直接运行 ${APP_ID}"
fi
echo "    诊断：./install.sh --doctor"
echo "    卸载：$( [ "$MODE" = "user" ] && echo "./install.sh --user --remove" || echo "sudo ./install.sh --remove" )"
