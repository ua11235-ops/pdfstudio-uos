#!/usr/bin/env bash
# 下载 UOS 能直接用的 Linux wheel 包（离线安装用）
#
# UOS 的 apt 源要系统激活才可用，pip 又常常没装，最省事的办法是：
# 在一台有网的电脑上把 wheel 下好，整个 wheels/ 目录拷到 UOS，
# 安装脚本会自动发现并离线安装，完全不碰 apt 和网络。
#
#   ./fetch_wheels.sh                  # 默认下 Python 3.7 的（UOS 20 自带）
#   ./fetch_wheels.sh --py 38          # 指定 3.8
#   ./fetch_wheels.sh --py 37,38,39    # 一次下多个版本
#   ./fetch_wheels.sh --py all         # 3.7 ~ 3.11 全下（约 400MB）
#
# 在 Windows / macOS / Linux 上都能跑，下的是 x86_64 Linux 的 wheel。

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${SCRIPT_DIR}/wheels"
PLATFORM="manylinux2014_x86_64"
INDEX="${PDFSTUDIO_PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"

PY_VERS=""
FORCE_PY=""

info() { printf '==> %s\n' "$*"; }
ok()   { printf '    ✓ %s\n' "$*"; }
warn() { printf '!! %s\n' "$*"; }
dim()  { printf '    %s\n' "$*"; }

usage() {
    cat <<TXT
用法：${0} [选项]

  --py 37            要下哪个 Python 版本的 wheel（默认 37）
                     可写多个：--py 37,38,39   或   --py all
                     all = 3.7 3.8 3.9 3.10 3.11
  --platform NAME    目标平台（默认 manylinux2014_x86_64）
  -o, --out DIR      输出目录（默认 ./wheels）
  --python PATH      指定用哪个 Python 的 pip 去下载
                     （自动挑的 pip 有问题时用这个）
  -h, --help         显示本帮助

对应关系：
  UOS 20 自带的 python3 是 3.7  →  --py 37
  自己装过 3.8 / 3.10 的         →  --py 38 / --py 310

环境变量：
  PDFSTUDIO_PIP_INDEX  换 pip 源，默认清华镜像
TXT
}

while [ $# -gt 0 ]; do
    case "$1" in
        --py)         PY_VERS="$2"; shift ;;
        --py=*)       PY_VERS="${1#*=}" ;;
        --platform)   PLATFORM="$2"; shift ;;
        --platform=*) PLATFORM="${1#*=}" ;;
        -o|--out)     OUT_DIR="$2"; shift ;;
        -o=*|--out=*) OUT_DIR="${1#*=}" ;;
        --python)     FORCE_PY="$2"; shift ;;
        --python=*)   FORCE_PY="${1#*=}" ;;
        -h|--help)    usage; exit 0 ;;
        *) warn "未知参数：$1"; echo; usage; exit 2 ;;
    esac
    shift
done

[ -n "$PY_VERS" ] || PY_VERS="37"

case "$PY_VERS" in
    all|ALL) PY_VERS="37 38 39 310 311" ;;
    *,*)     PY_VERS="$(printf '%s' "$PY_VERS" | tr ',' ' ')" ;;
esac

# ---------------------------------------------------------------- 找 pip
pip_ver_of() {
    "$1" -m pip --version 2>/dev/null | sed -n 's/^pip \([0-9][0-9.]*\).*/\1/p'
}

# 按 pip 版本从高到低列出候选解释器。
# 跨平台下载（--platform + --python-version）在不同 pip 版本上行为不一样，
# 比如 pip 26.1.x 会报 "from versions: none"，26.2.x 就正常，
# 所以这里不赌某一个，从新到旧挨个试。
list_pip_pythons() {
    local c p v
    for c in python3 python python3.13 python3.12 python3.11 python3.10 python3.9 python3.8 python3.7; do
        p="$(command -v "$c" 2>/dev/null || true)"
        [ -n "$p" ] || continue
        v="$(pip_ver_of "$p")"
        [ -n "$v" ] || continue
        printf '%s %s\n' "$v" "$p"
    done | sort -Vr -k1,1 | awk '{print $2}' | awk '!seen[$0]++'
}

PIP_CANDIDATES="$(list_pip_pythons)"

# 手动指定优先，自动挑的 pip 有问题时用它兜底
if [ -n "$FORCE_PY" ]; then
    if [ -z "$(pip_ver_of "$FORCE_PY")" ]; then
        warn "指定的解释器没有可用的 pip：${FORCE_PY}"
        exit 1
    fi
    PIP_CANDIDATES="$FORCE_PY"
fi

if [ -z "$PIP_CANDIDATES" ]; then
    warn "没找到任何带 pip 的 Python"
    dim "请先安装 Python 3 和 pip，或者换一台有 python3 + pip 的机器"
    exit 1
fi

ok "pip 源：${INDEX}"

mkdir -p "${OUT_DIR}"

# ---------------------------------------------------------------- 下载
# 用日志文件而不是管道：`cmd | sed` 的退出码是 sed 的，
# pip 失败了也会显示"完成"。
download_version() {
    local py="$1" v="$2" spec="$3" quiet="${4:-0}"
    local log rc
    log="/tmp/pdfstudio_wheels_${v}.$$.log"
    rc=0
    # 不传 --abi：让 pip 按 python-version 自己推断 abi 集合。
    # 显式传 --abi cp37m 反而会漏掉 abi3 的 PyQt5 轮子。
    "$py" -m pip download \
        --only-binary=:all: \
        --platform "${PLATFORM}" \
        --python-version "${v}" \
        --implementation cp \
        -d "${OUT_DIR}" \
        -i "${INDEX}" \
        PyQt5 "${spec}" > "$log" 2>&1 || rc=$?
    if [ "$rc" -eq 0 ]; then
        sed -u 's/^/    /' "$log"
    elif [ "$quiet" -eq 1 ]; then
        grep -E "ERROR" "$log" 2>/dev/null | sed -u 's/^/    /' || true
    else
        sed -u 's/^/    /' "$log"
    fi
    rm -f "$log"
    return "$rc"
}

# 一个解释器把请求的版本全下完才算成功
download_all() {
    local py="$1" quiet="$2" v minor vdisp spec fail=""
    for v in $PY_VERS; do
        case "$v" in
            3.*) v="${v//./}" ;;   # 允许写 3.7 这种形式
        esac
        minor="${v#3}"
        vdisp="${v:0:1}.${v:1}"

        if [ "$minor" -le 7 ] 2>/dev/null; then
            spec="pymupdf==1.22.5"
        elif [ "$minor" -eq 8 ] 2>/dev/null; then
            spec="pymupdf<=1.23.26"
        else
            spec="pymupdf"
        fi

        echo ""
        info "Python ${vdisp}（PyMuPDF 用 ${spec}）"
        if download_version "$py" "$v" "$spec" "$quiet"; then
            ok "Python ${vdisp} 完成"
        else
            warn "Python ${vdisp} 失败"
            fail="${fail} ${vdisp}"
        fi
    done
    [ -z "$fail" ] || { FAILED_VERS="$fail"; return 1; }
}

SUCCESS=0
FAILED_VERS=""
FIRST=1

for PIP_PY in $PIP_CANDIDATES; do
    PV="$(pip_ver_of "$PIP_PY")"
    if [ "$FIRST" -eq 1 ]; then
        echo ""
        info "使用解释器：${PIP_PY}（pip ${PV}）"
        FIRST=0
        download_all "$PIP_PY" 0 && SUCCESS=1 && break
    else
        # 重试时不刷屏，只打错误行
        echo ""
        info "换一个 pip 再试：${PIP_PY}（pip ${PV}）"
        download_all "$PIP_PY" 1 && SUCCESS=1 && break
    fi
done

# ---------------------------------------------------------------- 汇总
echo ""
info "结果"

COUNT=0
if [ -d "${OUT_DIR}" ]; then
    COUNT="$(ls -1 "${OUT_DIR}"/*.whl 2>/dev/null | wc -l | tr -d ' ')"
fi

if [ "$COUNT" -gt 0 ]; then
    ls -1 "${OUT_DIR}"/*.whl 2>/dev/null | while IFS= read -r f; do
        dim "$(basename "$f")  ($(du -h "$f" | cut -f1))"
    done
    TOTAL="$(du -sh "${OUT_DIR}" 2>/dev/null | cut -f1)"
    ok "共 ${COUNT} 个文件，${TOTAL}"
fi

echo ""
echo "  下一步：把整个 wheels 目录拷到 UOS，和项目放在一起："
echo "    pdfstudio-uos/packaging/wheels/"
echo "  然后正常执行安装，脚本会自动发现并离线安装："
echo "    sudo ./packaging/install.sh"
echo ""

if [ "$SUCCESS" -eq 0 ]; then
    warn "下载没成功${FAILED_VERS:+（失败版本：${FAILED_VERS# }）}"
    dim "常见原因：本机访问不了 pypi 镜像，或者所有 pip 版本都有问题"
    dim "换个源试试：PDFSTUDIO_PIP_INDEX=https://mirrors.aliyun.com/pypi/simple ${0}"
    dim "也可以直接到 UOS 本机跑这个脚本（本平台下载不需要跨平台参数）"
    exit 1
fi

ok "全部完成，可以把 wheels 目录拷走了"
