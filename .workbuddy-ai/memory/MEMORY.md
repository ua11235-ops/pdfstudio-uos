# 项目长期记忆

## PDF Studio（`pdfstudio-uos/`）

用户要一个**能在统信 UOS 上运行的 PDF 编辑软件**，已交付完整项目。

> **项目位置（2026-11-01 起）**：
> `C:\Users\ua11235\Documents\deepseek-harness\default-workspace\pdfstudio-uos`
> （原 `C:\Users\ua11235\WorkBuddy AI\2026-10-27-22-20-43\pdfstudio-uos`，已迁移，
> 项目记忆就在本项目内 `.workbuddy-ai/memory/`）

### ⚠ 工作区里起不了任何 Python 进程（每次会话都要注意）

`default-workspace` 下所有 venv 的 `python.exe` 都报
`did not find executable at <base python>`（退出码 103），PyInstaller 打的
exe 在里面也起不来（自检报"颜色 0 种"）。同一份文件复制到 `%TEMP%` 或
`C:\Users\ua11235\Documents\` 下完全正常。已排除磁盘、重解析点、目录名、
venv 损坏、文件占用、TEMP 变量等原因。

**验证必须在工作区外做**：
- 解释器：`C:\Users\ua11235\.dsh-venvs\pdfstudio\Scripts\python.exe`
  （PyMuPDF 1.24.14 + PySide6 6.12 + PyInstaller 6.22.3，别放回工作区）
- 项目副本：`C:\Users\ua11235\.dsh-venvs\proj_verify`（跑测试/打包用）
- 源码与交付物留在工作区，改完同步过去再跑

> 在工作区里看到"测试通过"是不可信的——程序可能根本没跑起来。

- 启动：`python3 run.py [文件.pdf]`；打包：`packaging/install.sh` / `build_deb.sh`
- 测试：`python3 tests/smoke_core.py`（39 项，无需 GUI）、
  `python3 tests/ui_smoke.py`（28 项，含真实鼠标拖拽/框选、真实渲染截图）、
  `python3 tests/_audit_thumbs.py`（缩略图专项审计，25 个场景，开发时手动跑）、
  `python packaging/windows/_test_install.py`（Windows 装/卸端到端，47 项）
- 发行包：`python3 packaging/make_release.py [--with-wheels]` → `packaging/build/`
  （**给 UOS 用户的必须是 79MB 那个**，363K 的纯源码包在 UOS 上装不上依赖）
- **Windows 版**：`packaging/windows/`，PyInstaller 单目录 + PowerShell 安装脚本。
  构建：`python -m PyInstaller packaging/windows/pdfstudio.spec --noconfirm
  --distpath packaging/windows/distN --workpath packaging/windows/buildN`
  （N 递增，别复用旧目录），再 `python packaging/windows/make_zip.py` → 42.8MB zip。
  验证：`PDFStudio.exe --selftest 图.png`（含渲染+打印链路，返回码即结果）。
  **注意**：`make_zip.py` 会自动挑最新的 `dist*`，旧目录留着不影响
- 跨平台现状：5619 行 Python **零平台分支**（全仓只有 run.py 的 shebang 是
  Linux 风格）；打印用 QPrinter，字体链已含 Microsoft YaHei UI，
  `desktop_dir()` 已兼容 `Desktop`/`桌面`。整套测试本来就跑在 Windows 上，
  所以"转 Windows"实际是**打包问题**，不是移植问题。仅 `packaging/*.sh`
  1246 行是 Linux 专属
- 开发环境：`C:\Users\ua11235\.dsh-venvs\pdfstudio\Scripts\python.exe`
  （**不要**把 venv 放在工作区里，见上面那条），PyMuPDF 1.24.14 +
  PySide6 6.12 + PyInstaller 6.22.3
- 依赖安装走清华镜像才快：`-i https://pypi.tuna.tsinghua.edu.cn/simple`
- **沙箱 Python 环境每次会话可能被重置**（只剩 pypdf），清华镜像也可能不通。
  这时去 `~/AppData/Local/pip/cache/http-v2` 翻缓存：每个 `.body` 就是一个 wheel，
  按 `{name}-{ver}-{WHEEL 文件里的第一个 Tag}.whl` 改名后
  `pip install --no-index --find-links <目录>` 可以完全离线装回 PySide6/PyMuPDF/PyInstaller。
  坑：`altgraph` 的第一个 Tag 是 `py2-none-any`，要改成 `py3-none-any`
- `install.sh` 支持 `--user` / `--remove` / `--doctor` / `-y` / `--no-deps`，
  环境变量 `PDFSTUDIO_PYTHON` 可强制指定解释器

### 安装脚本约定

- 依赖检测必须遍历**所有** `python3.x`，不能只看第一个 `python3`
  （用户遇到的「缺少 pymupdf」几乎都是依赖装在另一个解释器里）
- 判定解释器身份用 `sys.executable`，**不要** `realpath`，否则 venv 会被抹平
- 启动器要写死探测到的解释器绝对路径，并保留 PATH 兜底
- **UOS 的 apt 源是封闭的**（`professional-packages.chinauos.com` 需系统激活），
  `python3-pyqt5` 基本装不上，且 `python3-pip` 也要 apt 装 → 别指望 apt。
  UOS 上真正可行的是「离线 wheel」和「pip + 国内镜像」两条路
- `packaging/fetch_wheels.sh` 在任意有网机器上下 Linux wheel，
  `packaging/wheels/` 存在时 install.sh 自动离线安装
- pip 命令一律带 `--timeout 60 --retries 3 -i 镜像`，且**不要吞掉输出**，
  否则用户看到的就是「卡住」

### 发行包（`packaging/make_release.py`）

- **实现在 Python 里，`make_release.sh` 只是转发壳**。开发机是 Windows、没有 bash，
  shell 版根本跑不起来 → 实际后果是"发行包只能靠人记得去别处重打"，
  交付的 79MB 包停在 10-28，连 10-29 加的合并功能都不在里面，而本机测试全绿。
  脚本必须能在开发机上直接跑，"记得重新打包"才成立
- 打完包**默认自检**（`--no-verify` 才关）：必需模块缺一个、或
  `packaging/windows/dist*/` 的构建残留混进来，直接返回非 0。
  不能做成需要记得加的开关——出事的正是"打了包但没人核过"
- 排除规则按**路径段**判断，不按字符串前缀（`./sample` 会误伤 `./samples`）；
  PyInstaller 的 `dist*/build*` 按前缀匹配，下次换 `dist9` 也自动排除
  （不排除的话包会从 79MB 涨到 236MB）
- tar 里要**显式写 mode=755**：源码在 Windows 上维护，没有 Unix 执行位，
  不写进 tar，UOS 解包后 `sudo ./packaging/install.sh` 会 Permission denied。
  顺手把 uid/gid 归零（原来带着开发机的 197609）
- 给 UOS 用户的是 **79MB 带 wheel 那个**；363K 的纯源码包在 UOS 上装不上依赖
- 对应回归测试：`smoke_core.py` 最后一项「发行包收集规则」。破坏性验证过三次
  （不排 dist/build、漏合并模块、`--with-wheels` 收不到 wheel）都会变红。
  **破坏点要打在 `collect`/`should_skip` 上**，删掉 `REQUIRED` 里的需求项
  等于蒙上测试的眼睛，照样全绿（第一次就踩了这个）

### 代码约定

- `pdfstudio/core/` 不允许出现任何 Qt 代码，保持可无界面测试
- 任何文档修改必须包在 `doc.begin_change(label)` / `doc.end_change()` 之间，
  这样才有撤销
- 界面文案用简体中文；注释写中文，解释"为什么"而不是"做了什么"
- 目标运行环境是 UOS 20（Python 3.7 / PyQt5），不要用 3.8+ 语法
- **`QListWidget` 开了 `setUniformItemSizes(True)` + IconMode 时，
  任何动态 `addItem` 都必须同时 `setIcon`**。没有图标的条目 sizeHint 极小，
  会把整列尺寸拖垮（缩略图被压扁、点不中），而且事后补图标也不会恢复，
  必须调 `doItemsLayout()` 重排
- 侧栏刷新有 350ms 防抖（`_panel_timer`），写 UI 测试时 `pump` 要等够
- **缩略图必须画到固定尺寸画布上**（`render_page_pixmap()`，
  `min(THUMB_WIDTH/w, THUMB_HEIGHT/h)` 后居中留白）。按宽度算缩放会让
  图标高度随页面比例浮动，撞上固定的 `gridSize` 就被裁掉上下、间距也乱
- **白底页面在浅灰画布上看不出边界**，一屏几十个缩略图时分不清页码对应关系。
  截图里会误判成"缩略图被压扁了"（实测尺寸全对）。用
  `render_page_pixmap(border="#c2c8d4")` 描一圈细线
- `gridSize` 里已经含了间距，再 `setSpacing(4)` 会白吃掉一列

### 合并功能（`core/merge.py` + `ui/merge_dialog.py`）

- **页序只有一份真相**：`MergePlan.order`，每项 `(源文件下标, 源内页码)`。
  拖拽/删页只改这张表，源文件不动 → 反复调整不累积损失，也不需要撤销栈。
  源文件清单只管「有哪些文件」，**不做第二套顺序**，否则两边会打架
- 写文件时 `_runs()` 把连续页压成区间再 `insert_pdf`，300 页 1.8 秒
- `remove_source()` 必须把后面源的下标整体减 1，否则页序表指向错的文件；
  界面侧对应要 `_rebuild_preview()` 重挂所有条目
- 缩略图缓存的 key 用 `(文件路径, 页码)`，**不能用源下标**——移除文件后下标会前移
- 加密源在 `add_source()` 就抛 `PdfError(code="password")`，不要等到写文件才报

#### 拖拽排序（踩过的坑）

- **不要用 Qt 内置拖拽**（`setDragEnabled(True)` + `DragDrop`/`InternalMove`）：
  它要进 `QDrag::exec()`，那是**平台级模态循环**。实测本机上 startDrag 确实被
  调用，但 exec 进去之后松手毫无反应、进程卡在循环里出不来——这正是用户说的
  「鼠标拖拽还是没能成功」。更糟的是这个模态循环自动化测试进不去，只能覆盖
  exec 之外的代码，于是「改完测试全绿、用户还是拖不动」连续发生了两轮
- **现在的做法：拖拽自己实现，完全不碰 QDrag**。
  `setDragEnabled(False)` + `NoDragDrop`，改由 `mousePressEvent` 记起点、
  `mouseMoveEvent` 超过 `startDragDistance()` 转拖拽态、
  `mouseReleaseEvent` 调 `apply_drop()`。没有模态循环、没有平台差异，
  **测试能用 QTest 真实鼠标事件把整条链路跑通**
- `setAcceptDrops(True)` 仍要保留：从文件管理器拖 PDF 进来是另一套事件
- 拖回原地要给提示（`dragFinished` 信号 → 状态栏「顺序没有变化」），
  否则用户分不清「没搬动」和「功能坏了」
- 单纯点击（没超拖拽阈值）绝不能搬行，否则点选就成了误操作
- 落点规则看**格子后半**（下方或右方 → 插到后面）。只判「插到前面」的话，
  第 1 格拖到第 2 格等于原地不动，看着还是拖不动
- IconMode 下 Qt 不画落点指示线，`setDropIndicatorShown(True)` 等于没开，
  落点线要自己在 `paintEvent` 里画

#### 两处拖拽共用同一套纯函数

`side_panel.py` 里的 `drop_placement` / `is_noop_move` / `reorder_indices`
是无 Qt 依赖的纯函数，**界面和测试都不用自己再算一遍**：

- 合并窗口（`merge_dialog.py`）：搬条目 → 改 `MergePlan.order`
- 主界面缩略图（`ThumbnailList`）：算出新页序 → 发 `pagesReordered(order)`
  → `MainWindow.reorder_pages()` 包 `begin_change` + `pageops.reorder_pages()`
  → `doc.select(order)`，撤销栈里只留一帧「调整页序」

缩略图拖拽的两个约定：
- **拖拽本身不算文档修改**，真正的改动发生在 `MainWindow.reorder_pages`，
  所以撤销栈只有一条；撤销后停在哪一页按 `order.index(current)` 换算，
  用户看到的是「同一份内容」，不是「同一个页码」
- `refresh_all()` 会重建条目，`_pending` 按页码索引；拖拽后由主窗口
  `end_change` → `_panel_timer` 防抖刷新，缩略图自动按新页序重画

### 缩略图拖拽改页序（2026-11-02）

- `ThumbnailList` 自己处理鼠标（同合并窗口），松手发 `pagesReordered(order)`，
  `order` 是"新第 i 位放原来第几页"
- **拖拽本身不算文档修改**：真正的改动在 `MainWindow.reorder_pages()`，
  包 `begin_change` → `pageops.reorder_pages()` → `end_change`，
  撤销栈里只有一帧「调整页序」
- 撤销后停在哪一页按 `order.index(current)` 换算——用户看到的是同一份内容，
  不是同一个页码
- 纯函数 `drop_placement` / `is_noop_move` / `reorder_indices` 无 Qt 依赖，
  界面和测试共用，别各写一套
- 断言要看**文档里每页的实际文字**，不能看界面标签：标签重编号对了、
  底层页没换，是典型假绿

### 缩略图两种手势（2026-11-03）

缩略图上有两种按住拖动，**必须互斥**，否则会同时跑：

| 按下位置 | 手势 | 结果 |
| --- | --- | --- |
| 落在缩略图上 | 拖页排序 | 蓝色竖线标落点，松手改页序 |
| 落在空白处 | 框选 | 半透明蓝框，选中框内页面，**绝不动页序** |

- 判定**只在越过 `startDragDistance()` 那一刻做一次**，之后不改：
  中途换手势会让用户觉得枪口乱跳
- 越过阈值前**不要把 mouseMove 转给基类**。旧代码在阈值内统一 `super()`，
  基类于是开始橡皮筋框选，而我们在同一帧也算落点发重排信号 →
  用户看到「拖动和框选重复了」。现在阈值内直接 return，什么都不做
- **框选也自己实现，不用基类橡皮筋**。实测裸 `QListWidget`（IconMode /
  ListMode 都一样）的框选在 QTest 送事件时选不中任何条目，等于这条路径
  无法自动化验证；自己算命中 + 自己画框，既能测也不受平台差异影响
- 框选时按**选中集合整体重算**（`clearSelection()` 再按命中重选），
  不能只追加：框子缩小回去时旧选中要能退掉
- 框选期间**不要让 `currentRow` 跟着跳**，否则正文会一页页乱翻

### 测试约定

- 验证测试有效性的唯一标准：**把修复注释掉，确认测试变红**。
  查 icon 非空、等渲染完成再量尺寸，这类断言都会在 bug 存在时照样通过
- **破坏性验证要精确命中**：`str.replace(..., 1)` 遇到重复片段会改错地方，
  白验证一轮。用带唯一上下文的 old_string 并 `assert old in s`
- 缩略图校验用 `tests/_thumb_probe.py` 的 4×4 颜色指纹比对，
  样本 PDF 必须**每页颜色明显不同**，否则白底黑字分不出"画错页"
- 期望值必须从**当前文档实际渲染结果**取，不能按索引推算
  （插入空白页/旋转后，索引与内容的对应关系就变了）
- 测「压扁」必须在**操作刚结束、图还没画完**的窗口期量；
  `settle()` 等渲染完成后 Qt 会自己重排，什么都查不出来
- **`QListWidgetItem` 移动时图标跟着 item 走**，所以「拖完检查图标对不对」
  在已渲染完的情况下永远通过（假绿）。要抓串页必须在**还有未渲染页时拖**
- **断言配置 ≠ 断言行为**。旧测试查 `dragEnabled()`、`dragEnterEvent` 是否
  被接受——那测的是「配置对不对」，真正的故障（`QDrag::exec` 卡死）在这类
  断言面前完全隐形。换成 QTest 发真实鼠标事件、直接查页序变没变，才有牙齿
- **有时"测试挂死"本身就是正确答案**：破坏性验证时把拖拽退回 Qt 内置实现，
  `ui_smoke.py` 直接挂死不返回。所以破坏验证的子进程必须带 timeout，
  超时判为「抓到了问题」而不是「脚本坏了」

### Windows 打包与安装脚本（踩过的坑都在这）

- **`.bat` 必须 CRLF + 无 BOM**。只有 LF 时 cmd 按错误偏移解析：
  `setlocal` → `etlocal`、`echo.` → `ho.`，并连带 `cd /d "%~dp0"` 失效，
  最终报「找不到 PDFStudio.exe」。**`.ps1` 相反，必须 UTF-8 带 BOM**，
  否则 PS 5.1 按 ANSI 解析，中文全乱码
- **`.bat` 里的 `rem` 注释行必须纯 ASCII**。`chcp 65001` 下 cmd 解析含中文的
  `rem` 行会错位，把后半句当命令执行（`'文的参数错误…' is not recognized`）。
  中文只能放在 `echo` 里。这条可以静态检查：`bad_rem_lines()`
- **`.bat` 结尾的 `pause` 会把 ERRORLEVEL 冲成 0**，安装失败也返回成功。
  必须先 `set "RC=%ERRORLEVEL%"`，再 `pause`，最后 `exit /b %RC%`。
  另外 `pause` 会让自动化调用卡死 → subprocess 要传 `stdin=DEVNULL`
- `_fix_scripts.py` 统一编码换行，且 `make_zip.py` 打包前会**自动调用**它。
  不能靠"记得手动跑"——用 bash 跑 .bat 看不出问题，只有 cmd 才暴露
- **`New-Item -Path <注册表键> -Force` 是"重建键"，会清空默认值和所有子键**，
  不是"已存在就跳过"。用它处理 `.pdf` 会毁掉系统放的 `OpenWithProgids`；
  用它处理备份键会把刚写的备份清掉。一律先 `Test-Path` 再建
- **覆盖安装不能覆盖关联备份**：第二次装时 `.pdf` 已是自己的 ProgId，
  若把备份改成自己的值，卸载会把 `.pdf` 还原成一个刚被删掉的 ProgId，
  双击 PDF 变成"没有关联"。备份只记「别人」的值
- 卸载清 `.pdf` 时若装前没有关联，**只清默认值，别整键删除**（键里可能有子键）
- PowerShell 运算符优先级：`-not $a -eq $b` 是 `(-not $a) -eq $b`，逻辑反了
- `winreg.SetValueEx` 是 **5 个参数** `(key, 名, reserved, 类型, 值)`
- **程序目录要能自动找**：`PDFStudio\` 同级是标准布局，但要兜住
  「多套一层」「子目录直接摊开」「源码目录的 `dist3/PDFStudio`」三种。
  源码目录里程序在 `dist3`，不认这个的话在开发机点 `安装.bat`
  永远报"找不到 PDFStudio.exe"，看起来像打包坏了
- **找不到目标时必须打印"我看到了什么"**（目录清单 + 原因判断），
  否则用户只能描述现象、我只能猜。诊断要给出 `-AppDir` 手动指定用法
- 卸载删自身目录分两步：先删除脚本外全部内容，再交后台 cmd 删空目录
- 测试断言查"命令不存在"要**同时覆盖中英文**：`chcp 65001` 之后
  系统消息会变英文，只查「不是内部或外部命令」会漏掉一半
- **测试必须解压真实 zip 来跑**：源码目录里程序在 `dist3/PDFStudio`，
  压缩包里才是 `PDFStudio/`，在源码目录跑安装脚本必然假失败
