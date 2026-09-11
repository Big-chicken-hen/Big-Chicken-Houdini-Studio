# Big-Chicken Houdini Studio

一个独立的 Houdini 创作工作室：原生 Qt 启动器与 Python Panel，Codex App Server 负责对话和推理，Houdini 主线程负责批量 HOM，runtime 保存场景身份与操作收据。它不依赖旧 HIA 安装目录。

当前 **0.1.0-rc.1 已获准日常 RC 试用和定向测试**，尚未公开发行。R1–R3 已技术合并；R4 保持 Draft，等待新入口与独立标准用户验收。本轮按 [固定节点流 Launcher 审批](docs/launcher-node-flow-brief.md) 实现 Account → 场景分支 → Launch；NET-1、同一 Turn 内追加引导及既有验收证据保留，Panel 与执行架构保持不变。

已验证组合为 Windows 11 x64 / Houdini FX 22.0.368 / Codex 0.153.4。其他满足接入条件的 Houdini 22 系列为 Untested，逐次确认后可试测；无法确认的现场事实保留 Unknown。普通用户只从安装器创建的开始菜单入口启动，使用随包 Codex。外部 Codex 服务需要用户自己的有效 Clash 配置，端口由用户环境决定；Studio 不修改系统代理。以下源码 setup 仅供开发。既有 [模型实验结论](docs/model-acceptance-results.md) 保持不变。

## 从源码在 Windows 开始（开发者）

1. 将整个项目放在可写目录。支持空格和中文路径；不要放进 Houdini 安装目录。
2. 准备 Python 3.10+、带 PySide6 的 Houdini GUI 安装，以及本项目固定使用的 **Codex CLI 0.153.4 原生可执行文件**。Houdini Panel 使用 Houdini 自带的 PySide6，不向它安装 Qt。
3. 双击 **`Setup Studio.cmd`**。这一步在本项目 `.runtime/venv` 安装产品和启动器的 PySide6；不会修改用户的 Houdini 或 Codex 配置，也不会启动 Houdini、登录或导入知识。
4. 双击 **`Studio.exe`**（setup 会生成）。安装版的开始菜单也指向同名 EXE。Account 节点显示账号与 Codex 状态，必要时完成官方浏览器登录；从 Empty／Open／Recent 中选择目标，再点击 Launch 节点的“启动 Houdini”。选择、双击或拖入 HIP 都只选定目标。程序路径和诊断使用顶部“设置”“诊断”入口。
5. 在 Houdini 面板标签旁点击 **＋ → New Pane Tab Type → Big-Chicken Studio**，直接打开 Studio。已有 Python Panel 也可在其界面选择栏中选择 **Big-Chicken Studio**。账户、模型和会话通过原生 Codex App Server 处理。

日常启动不安装依赖、不构建索引、不恢复 Goal。关闭启动器不会关闭已经打开的 Houdini；关闭这个 Houdini 后，其 supervisor 清理自己启动的 Codex/Bridge。已有的用户 Houdini 进程不参与管理。

正式启动沿用平时 Houdini 的用户配置，包括布局、配色和快捷键；Studio 不复制或改写这些配置。测试环境继续使用独立偏好目录，避免影响日常工作。

启动过程保持节点流，Launch 节点显示实际阶段；只有目标场景确认打开且所需试测确认完成后，才默认最小化 Launcher。此偏好可在设置中关闭。Panel 将模型与 effort 放在 Composer 的常驻组合入口内，工作期间可继续发送引导，Send 和 Stop 同时可见。产品图标只使用批准的 Lucide SVG；Launcher 的 Chicken 字样使用随包 Changa One Italic，其余字体保持原有选择。

新输出优先采用本次明确指定的位置，其次保留已有节点的输出设置。Studio 默认输出在已保存 HIP 同目录的 `BigChickenStudio/<场景名>/renders`、`exports` 或 `assets`；未保存场景使用用户缓存中的临时输出。默认位置在执行时解析，后续输出跟随成功的 Save As；历史文件不搬移。路径解析本身不代表已经完成渲染或导出。

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
本次已运行的检查与尚未验证的真实会话范围见 [集成验收记录](docs/verification.md)。

## 数据与执行边界

源码和安装依赖留在安装目录。正常启动将工作空间、收据、附件与原生 Codex home 放在平台用户持久数据目录，日志和临时输出放在独立缓存目录；Windows 使用系统解析的 LocalAppData 下 `BigChickenStudio/state` 与 `BigChickenStudio/cache`。旧 `.runtime` 数据原地保留，不自动迁移、删除或改写。开发测试使用本 checkout 的 `.runtime`，不使用真实用户状态。

工作空间 ID 与安装根、启动 session、scene epoch、operation ID 分开。保存或 Save As 不搬移活跃工作空间与原生会话 cwd。Codex 原生 Thread/Turn 和自动压缩保留；本产品不另外生成聊天摘要或自动记忆。已完成的真实创作验证不代替尚未完成的独立标准用户安装、升级与卸载链路，也不认证未测试的跨屏 DPI 组合。

本地服务仅绑定 `127.0.0.1`。每次启动生成新的会话 token，只通过子进程环境传递。通用 HOM 是受信任的本机自动化，可能产生文件或进程副作用；Undo 不代表可以安全重放。丢失响应后查询原 operation ID，不自动重跑脚本。Codex Stop 与 Houdini 的执行状态分别展示。

CI 覆盖 `main`、`release/**` 和 PR，在 Windows/Linux 的 Python 3.10/3.13 跑一个静态正确性检查、小型 unittest 和离线导入 smoke。Linux CI 只验证后端可移植性；完整桌面启动交付目标是 Windows。
