# 2026-09-05 集成验收记录

交付为 Big-Chicken Houdini Studio 0.1.0 开发预览，主目录 `E:\Big-Chicken-Houdini-Studio`。三个独立 Codex 工作树分别交付 UI、启动安装和执行协议，总审审阅后合入新 Git 主线。完整 Pro 诊断保留在 `docs/pro-diagnosis.md`。

## 已实际验证

- 新主目录中执行显式 setup，安装到 `.runtime/venv`，使用 Python 3.10.11、PySide6-Essentials 6.8.3 和 Ruff 0.12.12。Qt 使用已下载的完整 wheel，没有重复下载 Addons。
- 主线执行一次 `scripts/check.py`：Ruff 正确性检查通过，42 项 unittest 全部通过。覆盖 Bridge 延迟/丢失响应与原生终态、工作空间边界、Stop、队列容量、场景 epoch、收据失败、外部效果异常、操作 ID 重查、图片投影、启动进程归属和 Qt 非阻塞 HTTP 等。它们使用受控场景替身，不是假称真实 Houdini 任务。
- 用项目内 Qt 6.8.3 生成并审看启动器、对话、执行记录、项目决策四张离屏截图。最后补充启动器的实际渲染目录显示，仅重新渲染受影响的启动器。图像位于 `.runtime/previews`，Panel 内容为预览脚本明确注入的夹具，生产代码不注入演示历史。
- 原生 Codex 0.153.4 在独立且无凭据的项目内 `CODEX_HOME` 中完成 initialize、account/read、model/list、thread/start。MCP 启动事件返回 `ready`。未触发模型 turn 或登录。
- 实测新建空会话的完整历史读取返回 `list_turns is not supported yet`，metadata-only 读取返回 idle。Bridge 已针对该响应保留原生状态并注明历史暂不可用；最终再次实测创建、读取和 reconcile 均成功处理。
- 已从本机 Houdini 22.0.368 的只读 Python API 文件核对主线程调度入口、参数模板与 flipbook 所用方法存在。这只证明接口可用，不证明 GUI 行为。
- 主项目及三个工作树配置均为 `model_context_window=400000`、`model_auto_compact_token_limit=350000`。Bridge 将这两个值显式传给新建/恢复的场景会话，原生 thread/start 接受了该配置。未修改用户全局配置，也没有将运行中会话的有效窗口声称为已测得。

## 尚未实测

真实 Houdini GUI 的 Panel 加载、已有 HIP 场景切换与主线程执行、实际 cook/viewport capture、Codex 登录与推理、跨启动的多轮历史恢复、模型看到原生 MCP 图片、真实进程崩溃及渲染交付端到端仍待真实会话验收。Windows 双击入口未以用户桌面操作测试，远端 CI 未运行，也未 push。

原生协议字段和已知空会话边界见 `contracts/codex/0.153.4/README.md`。启动入口为根目录的 `Start Studio.vbs`，安装及命令行替代入口见 `docs/installation.md`。既有用户 HIP、旧仓库和全局 Houdini/Codex 设置均不是本次修改目标。
