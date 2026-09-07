# 安装与交付

## 安装边界

分发单位是完整仓库或解压目录，必须保留 `src`、`houdini`、`scripts` 和 `pyproject.toml`。安装根默认按当前源码/入口的位置解析，也可用 `HIA_PROJECT_ROOT` 指定。普通场景工作在用户持久数据根的 `workspaces/<id>/work` 内，不能把插件源码目录当成创作项目。

Launcher 在 Windows 通过系统 Known Folder API 解析 LocalAppData，使用其中 `BigChickenStudio/state` 保存 workspace、ledger、附件、原生 Codex home 和场景索引，`BigChickenStudio/cache` 保存日志、临时图片及未保存场景的临时输出。两个根以 `BCS_DATA_ROOT`、`BCS_CACHE_ROOT` 传给子进程，各自保持 containment 检查；安装 venv 和资源不会跟随用户数据迁移。开发 fixture 显式使用 checkout 下 `.runtime`。

后端仅依赖 Python 标准库。独立启动器使用可选依赖 `PySide6-Essentials==6.8.3`（包含所需 QtWidgets/QtNetwork，不下载 Addons）；Houdini Panel 使用安装自带 PySide6。请使用带 PySide6 的 Houdini GUI 构建；不提供 PySide2 回退，也不修改 Houdini 的 Python 环境。项目附带 Python 3.10、3.11、3.13 的 UI-ready 接入目录，具体 GUI 构建仍需实测验收。

## 一次显式 setup

```powershell
# 默认包含启动器；-Python 接受现有 Python 可执行文件的完整路径
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Python "C:\路径 含空格\python.exe"

# 后端开发/CI 无需下载 Qt
python scripts/setup.py --backend-only --dev

# 离线环境：预先准备匹配 Python/系统的依赖 wheel，包括 setuptools
python scripts/setup.py --no-index --find-links ".runtime/wheels"
```

setup 在 `.runtime/venv` 建 venv，pip 缓存在 `.runtime/cache/pip`，构建临时副本在 `.runtime/tmp`。不改全局 pip 配置、不使用用户 site-packages，不复制或删除用户 HIP。再次运行 setup 是显式依赖维护，不清空工作空间和历史。

不从启动代码调用 setup。只装后端时，`launcher` 会提示安装 PySide6；CLI 的 workspace、memory、document、status、smoke 均不需要 Qt 或 Houdini。安装中断时保留现场，不自动删除不完整的 venv 或用户文件。

## Codex 选择与版本

本项目的协议契约固定为 **0.153.4**。Launcher 按明确 override、上次验证安装、安装内管理的工具链、PATH 与有限已知安装位置查找原生程序，验证版本和 App Server initialize。明确 override 无效时显示错误，不静默切换其他安装。环境缺失页可选择已有安装；路径覆盖选项在更多菜单的设置页中。选择 `codex.exe` 本体，不执行任意 `.cmd` / `.ps1` 包装器。也可设置 `BCS_CODEX_PATH`，或自行放置到 `.runtime/toolchains/codex/codex.exe`。没有默认下载或自动升级。

官方 [Codex CLI 说明](https://learn.chatgpt.com/docs/codex/cli) 提供安装方式；从官方分发渠道取得所需版本。项目使用原生 [Codex App Server](https://learn.chatgpt.com/docs/app-server) 的会话与账户接口；当前官方文档不代替固定版本的实际协议核对。首次使用在 Launcher 点击“使用 ChatGPT 继续”，由官方返回的地址打开系统浏览器；等待期间可取消或重新打开当前登录页，只有原生账号查询确认后才进入首页。网络失败显示尚未确认。setup 与 smoke 不登录、不发模型请求。

Windows 下，Studio 自有的登录和正式会话 Codex 进程都启用原生 `respect_system_proxy`，采用 Windows 已配置的系统代理。此开关仅通过子进程启动参数传入，不复制桌面 Codex 配置或认证，也不写入全局代理环境变量。启动参数的修复在新启动的 Studio 会话中生效。

短生命周期 onboarding 只查询账号及处理官方登录，不创建 Thread、模型任务、MCP 或 Houdini。它在正式启动前关闭，生产进程使用同一个已验证的 Codex 程序和同一个用户持久数据根下 `codex-home`。此目录由 Codex 管理认证与历史；Studio 不复制 token 或编辑凭证。旧安装的 `.runtime/codex-home` 原地保留，不自动迁移；界面不提供旧上下文浏览或 profile 切换流程。

## 启动与进程

双击 `Start Studio.vbs` 无控制台窗口。也可以运行：

Launcher 依次投影检查、必要的环境设置、必要的登录、最近场景首页和启动状态。确认正常时直接进入首页，不再展示成功检查表。打开一个本地 HIP 或空场景会直接激活；最近文件单击只选择，双击、Enter 或行内打开才激活。纯选择不创建工作空间，实际启动接纳时才分配或复用内部身份。再次打开已知 HIP 保持其关联；每次实际启动空场景使用独立身份。最近文件记录只来自实际启动及成功 Load/Save，条目菜单的移除操作不删除文件。

非首页拖入 HIP 只暂存一个待打开目标，完成登录后仍需明确激活。启动可能已经发生时页面保留原请求的查询动作，不能通过返回首页重新启动。目标场景确认打开后，默认约半秒最小化 Launcher，每个请求仅一次；用户正在查看详情时不抢走窗口。该偏好位于设置页。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/launch.ps1
# 排查启动器错误时显示控制台
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/launch.ps1 -Console

# 标准产品入口
.runtime/venv/Scripts/python.exe -m studio launcher

# 无启动器地明确打开新的 GUI session
.runtime/venv/Scripts/python.exe -m studio launch --workspace WORKSPACE_ID --houdini "C:\Houdini\bin\houdini.exe" --codex "C:\工具\codex.exe" --hip "C:\作品\场景.hip"
.runtime/venv/Scripts/python.exe -m studio status --session SESSION_ID
```

非 GUI 管理命令在未指定存储根时保留原安装 `.runtime` 行为。要管理新版 Launcher 的数据，应在该命令进程中明确传入同一 `BCS_DATA_ROOT` 和 `BCS_CACHE_ROOT`，不要靠复制数据库切换身份。

`python -m studio supervise --session SESSION_ID` 是内部入口，要求 launcher 传入新鲜 session 环境。不要手工保存、复制 token 或用旧 descriptor 重启 supervisor。`pythonw.exe` 只运行启动器；supervisor 和 MCP 使用同一环境中的控制台 `python.exe`，Windows helper 使用隐藏窗口标志，保留标准流。

launcher 可以退出，已启动的 Houdini 保持运行。supervisor 只等待它自己持有的 Houdini 子进程句柄，然后关闭自己创建的 Bridge/App Server；不按进程名或保存的 PID 搜索、终止其他 Houdini。supervisor 故障时不会自动杀 GUI、重载 HIP 或重放操作。状态文件里的 `ready` 只表示匹配的 runtime 完成登记；操作结论以 runtime 收据为准。`status` 读取保存的进程事实，不能证明进程在查询时仍活着。

Houdini 的 package、隔离首选项与临时目录只由子进程环境设置，不修改 Houdini 安装或全局用户配置。Runtime 注册与目标 HIP 成功打开分别显示；启动响应丢失后查询原 session，不重复启动 Houdini。

新输出位置按“本次明确位置 → 已有节点输出 → Studio 默认”解析。已保存场景的默认值为 HIP 同目录下 `BigChickenStudio/<场景名>/{renders,exports,assets}`；未保存场景使用用户缓存中的临时输出。成功 Save As 只改变后续默认位置，不搬历史文件、ledger 或活跃 Codex cwd。既有 HIP 的输出节点参数不会被 Launcher 改写。保留的显式 `HIA_RENDER_OUTPUT_DIR` 子进程配置不替代 Runtime 的执行时路径策略。

## 显式项目数据管理

```powershell
.runtime/venv/Scripts/python.exe -m studio memory --workspace ID record --body-file ".runtime/decision.txt"
.runtime/venv/Scripts/python.exe -m studio memory --workspace ID supersede --record-id OLD_ID --body "更新后的决策"
.runtime/venv/Scripts/python.exe -m studio memory --workspace ID delete --record-id ID_TO_DELETE
.runtime/venv/Scripts/python.exe -m studio memory --workspace ID export --output ".runtime/exports/decisions.json"
```

导出只创建新文件，不覆盖已有文件。document import 接受 UTF-8 TXT、Markdown、HTML 文档，要求提供来源与版本；FTS 只在明确导入时建立。不会默认索引插件开发文档，不安装 embedding，不把记忆写入与向量处理绑定。Houdini 关闭时仍可管理这些数据。

## 搬移与保留

更换安装位置前先正常关闭其 Houdini 会话。新布局的用户数据独立于安装位置，旧 `.runtime` 中的 workspace、原生历史、认证和图片引用必须原地保留，不自动移动、重新编号或改写；绝对 cwd 和历史图片路径不能靠搬文件猜测修复。源码分发不包含这些私有数据。外部 Houdini、Python、Codex 仍需安装或重新选择；venv 跨机器不保证可直接使用，依赖维护只在显式 setup 时进行。

## 验证范围

`scripts/check.py` 跑一次 Ruff 正确性检查（含未定义变量）和小型 unittest；`--pattern test_launcher.py` 可只跑启动边界。`scripts/smoke.py` 验证标准库后端可导入及 SQLite FTS5 能力，`--codex <path>` 可显式追加版本检查，`--ui` 只检查 PySide6 可导入。它们不启动 Houdini、不发 AI 请求、不读写用户 home 配置。

native Qt 离屏截图用于审查布局。Houdini 22.0.368 中已实测 Python Panel 注册、主线程节点批次、几何与参数回读，以及原生 Codex 登录和 Box 自然语言任务；具体证据见 [阶段验收记录](stage-readiness-results.md)。已有 HIP 场景切换、长 cook 中断、图片回传和渲染输出仍待验证，不承诺未经测量的速度提升。
