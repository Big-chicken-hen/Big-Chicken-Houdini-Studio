# 安装与交付

## 安装边界

分发单位是完整仓库或解压目录，必须保留 `src`、`houdini`、`scripts` 和 `pyproject.toml`。应用根默认按当前源码/入口的位置解析，也可用 `HIA_PROJECT_ROOT` 指定。普通场景工作在 `.runtime/workspaces/<id>/work` 内，不能把插件源码目录当成创作项目。

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

本项目的协议契约固定为 **0.153.4**；启动前仅运行所选原生程序的 `--version`，其他版本会得到明确提示。选择 `codex.exe` 本体，不选择 npm 的 `.cmd` / `.ps1` 包装器。可在启动器中浏览选择，也可设置 `BCS_CODEX_PATH`，或自行放置到 `.runtime/toolchains/codex/codex.exe`。没有默认下载、自动升级或旧项目盘符依赖。

官方 [Codex CLI 说明](https://learn.chatgpt.com/docs/codex/cli) 提供安装方式；从官方分发渠道取得所需版本。项目使用原生 [Codex App Server](https://learn.chatgpt.com/docs/app-server) 的会话与账户接口；当前官方文档不代替本项目固定版本的实际协议核对。首次真实使用时在 Panel 走原生登录；setup 与 smoke 不登录、不发模型请求。

Codex 子进程的 `CODEX_HOME` 指向本安装的 `.runtime/codex-home`，不会重写用户原来的 Codex 配置。它包含原生账户与会话数据，应随本安装的私有数据一起保护，不随源码分发。

## 启动与进程

双击 `Start Studio.vbs` 无控制台窗口。也可以运行：

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

`python -m studio supervise --session SESSION_ID` 是内部入口，要求 launcher 传入新鲜 session 环境。不要手工保存、复制 token 或用旧 descriptor 重启 supervisor。`pythonw.exe` 只运行启动器；supervisor 和 MCP 使用同一环境中的控制台 `python.exe`，Windows helper 使用隐藏窗口标志，保留标准流。

launcher 可以退出，已启动的 Houdini 保持运行。supervisor 只等待它自己持有的 Houdini 子进程句柄，然后关闭自己创建的 Bridge/App Server；不按进程名或保存的 PID 搜索、终止其他 Houdini。supervisor 故障时不会自动杀 GUI、重载 HIP 或重放操作。状态文件里的 `ready` 只表示匹配的 runtime 完成登记；操作结论以 runtime 收据为准。`status` 读取保存的进程事实，不能证明进程在查询时仍活着。

Houdini 的 package、用户偏好与临时目录只由子进程环境设置。不会把 package 写进安装或用户 home。渲染默认写到 `<app_root>/.runtime/cache`；显式 `HIA_RENDER_OUTPUT_DIR` 可以覆盖，启动结果会报告绝对路径。既有 HIP 的保存位置和输出节点参数不会被 launcher 修改。

## 显式项目数据管理

```powershell
.runtime/venv/Scripts/python.exe -m studio memory --workspace ID record --body-file ".runtime/decision.txt"
.runtime/venv/Scripts/python.exe -m studio memory --workspace ID supersede --record-id OLD_ID --body "更新后的决策"
.runtime/venv/Scripts/python.exe -m studio memory --workspace ID delete --record-id ID_TO_DELETE
.runtime/venv/Scripts/python.exe -m studio memory --workspace ID export --output ".runtime/exports/decisions.json"
```

导出只创建新文件，不覆盖已有文件。document import 接受 UTF-8 TXT、Markdown、HTML 文档，要求提供来源与版本；FTS 只在明确导入时建立。不会默认索引插件开发文档，不安装 embedding，不把记忆写入与向量处理绑定。Houdini 关闭时仍可管理这些数据。

## 搬移与保留

搬移完整应用时先正常关闭其 Houdini 会话，再复制完整目录及需要的 `.runtime` 私有数据；不要只复制 `src`。入口从当前位置解析 root，不硬编码驱动器。若用户设置过绝对的 `HIA_PROJECT_ROOT`、`BCS_CODEX_PATH` 或渲染目录，搬移后应调整它们。外部 Houdini、Python、Codex 仍需在新机器安装或重新选择。Python venv 跨机器并不保证可直接使用；显式运行 setup/修复依赖，保留已有工作空间和原生会话，不在日常启动自动修复。

## 验证范围

`scripts/check.py` 跑一次 Ruff 正确性检查（含未定义变量）和小型 unittest；`--pattern test_launcher.py` 可只跑启动边界。`scripts/smoke.py` 验证标准库后端可导入及 SQLite FTS5 能力，`--codex <path>` 可显式追加版本检查，`--ui` 只检查 PySide6 可导入。它们不启动 Houdini、不发 AI 请求、不读写用户 home 配置。

native Qt 离屏截图可审查布局，但不等于真实 Houdini GUI 验收。最终交付还需真实验证所选 Houdini 构建、Python Panel 加载、UI 主线程调度、Codex 登录/推理、已有 HIP、cook、图片回传和渲染输出。当前不宣称这些任务已经完成，也不承诺未经测量的速度提升。
