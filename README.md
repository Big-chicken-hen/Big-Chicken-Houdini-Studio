# Big-Chicken Houdini Studio

一个独立的 Houdini 创作工作室：原生 Qt 启动器与 Python Panel，Codex App Server 负责对话和推理，Houdini 主线程负责批量 HOM，runtime 保存场景身份与操作收据。它不依赖旧 HIA 安装目录。

当前版本是 **0.1.0 开发预览**。标准库测试和离屏 Qt 预览只证明各自覆盖的行为；真实 Houdini GUI、渲染及 Codex 推理端到端任务尚未完成验收。不要把启动器显示“已连接”当作场景操作完成。

## 在 Windows 开始

1. 将整个项目放在可写目录。支持空格和中文路径；不要放进 Houdini 安装目录。
2. 准备 Python 3.10+、带 PySide6 的 Houdini GUI 安装，以及本项目固定使用的 **Codex CLI 0.153.4 原生可执行文件**。Houdini Panel 使用 Houdini 自带的 PySide6，不向它安装 Qt。
3. 双击 **`Setup Studio.cmd`**。这一步在本项目 `.runtime/venv` 安装产品和启动器的 PySide6；不会修改用户的 Houdini 或 Codex 配置，也不会启动 Houdini、登录或导入知识。
4. 双击 **`Start Studio.vbs`**。创建工作空间，选择 Houdini、Codex 和可选的现有 HIP，再进入工作室。若系统禁用了 Windows Script Host，可运行 `scripts/launch.ps1`。
5. 在 Houdini 的 Python Panel 中选择 **Big-Chicken Studio**。账户、模型和会话通过原生 Codex App Server 处理。

日常启动不安装依赖、不构建索引、不恢复 Goal。关闭启动器不会关闭已经打开的 Houdini；关闭这个 Houdini 后，其 supervisor 清理自己启动的 Codex/Bridge。已有的用户 Houdini 进程不参与管理。

默认渲染输出目录是 **当前应用根目录的 `.runtime/cache`**。设置 `HIA_RENDER_OUTPUT_DIR` 可显式覆盖它；相对路径按应用根解析。启动结果和 session 的 `launch.json` / `status.json` 会报告最终路径。这是输出目录约定，不会静默改写已打开 HIP 的 ROP 参数。

## 命令入口

以下命令在项目根运行；先完成 setup。其他位置可用 `HIA_PROJECT_ROOT` 指定此安装，或传全局参数 `--app-root`。

```powershell
# 只安装标准库后端，不下载 PySide6；--dev 额外安装 Ruff
python scripts/setup.py --backend-only --dev

.runtime/venv/Scripts/python.exe -m studio launcher
.runtime/venv/Scripts/python.exe -m studio workspace create "我的作品"
.runtime/venv/Scripts/python.exe -m studio workspace list
.runtime/venv/Scripts/python.exe -m studio memory --workspace WORKSPACE_ID list
.runtime/venv/Scripts/python.exe -m studio memory --workspace WORKSPACE_ID record --body "场景单位为米"
.runtime/venv/Scripts/python.exe -m studio document --workspace WORKSPACE_ID import "help.txt" --source "本地帮助" --version "21.0"
.runtime/venv/Scripts/python.exe -m studio document --workspace WORKSPACE_ID lookup "hou.Node" --version "21.0"
.runtime/venv/Scripts/python.exe scripts/smoke.py
.runtime/venv/Scripts/python.exe scripts/check.py
```

完整安装、离线安装、直接启动、显式记忆导出和交付边界见 [安装与交付](docs/installation.md)。设计验收依据是 [用户 Pro 诊断](docs/pro-diagnosis.md) 和 [重建契约](docs/rebuild-brief.md)。

## 数据与执行边界

源码留在 `src`，安装依赖、日志、会话、附件、收据和工作空间留在 `.runtime`；工作空间 ID 与安装根、启动 session、scene epoch、operation ID 分开。Codex 原生 Thread/Turn 和自动压缩保留；本产品不另外生成聊天摘要或自动记忆。

本地服务仅绑定 `127.0.0.1`。每次启动生成新的会话 token，只通过子进程环境传递。通用 HOM 是受信任的本机自动化，可能产生文件或进程副作用；Undo 不代表可以安全重放。丢失响应后查询原 operation ID，不自动重跑脚本。Codex Stop 与 Houdini 的执行状态分别展示。

CI 覆盖 `main`、`release/**` 和 PR，在 Windows/Linux 的 Python 3.10/3.13 跑一个静态正确性检查、小型 unittest 和离线导入 smoke。Linux CI 只验证后端可移植性；完整桌面启动交付目标是 Windows。
