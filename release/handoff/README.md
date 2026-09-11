# Big-Chicken Houdini Studio

在 Houdini 中，通过 Codex 对话创建场景、调整参数，并在原作品上继续修改。

**Release Candidate** · **Windows 11 x64** · **原生 Houdini Panel**

[快速开始](#快速开始) · [环境要求](#环境要求) · [验收指南](验收指南.md) · [问题反馈](问题反馈.md)

---

## 快速开始

1. **安装** — 完整解压压缩包，双击 [Installer.exe](Installer.exe)。无需另外安装 Python、Node 或 Git。
2. **打开 Studio** — 从开始菜单打开 **Big-Chicken Houdini Studio**，日常入口统一为 `Studio.exe`。
3. **登录账号** — 保持 Clash 使用自己的有效配置，在 **Account** 节点完成 ChatGPT 官方浏览器登录。
4. **选择场景** — 在 **Empty / Open / Recent** 中选择目标，再点击 **Launch** 节点的“启动 Houdini”。
5. **开始创作** — 进入 Houdini 的 **Big-Chicken Studio Panel**，按界面提示授予本对话场景操作许可后发送请求。

**选择场景不会自动启动。** 点击、双击或拖入 HIP 都只选择目标，启动由 Launch 明确触发。

已有本项目开发环境时，直接使用项目根目录的 `Studio.exe`，无需再次安装此测试包。

## 环境要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 11 x64 |
| Houdini | 有效许可证；当前验证组合为 **Houdini FX 22.0.368** |
| 其他 Houdini 22 配置 | 以启动器的兼容状态为准；允许的 **Untested** 配置需明确确认试用 |
| Codex | 随包提供 **0.153.4**，默认使用 Bundled 版本 |
| 账号 | 使用自己的 ChatGPT 账号完成官方登录 |
| 网络 | Clash 保持有效配置，端口使用自己的设置 |

`Unknown` 表示尚未确认，不能视为已支持。无需复制开发者的代理配置，也不需要关闭 Clash 进行测试。

## 日常使用

- **场景续作**：通过 Open 或 Recent 选择 HIP，再点击 Launch。用 Save As 将作品保存到自己选择的位置。
- **熟悉的 Houdini 配置**：正式启动沿用原有布局、配色和快捷键，Studio 不复制或改写偏好文件。
- **自定义插件路径**：正常启动保留支持的 Houdini 插件搜索路径，并加入 Studio 的 package 目录；测试环境继续隔离。
- **场景产物**：从已保存 HIP 工作时，默认将生成的 VEX 源码、HDA、导出和渲染文件放在 `$HIP/BigChickenStudio/<场景名>/` 下对应目录；明确指定位置和已有节点输出优先。
- **执行期间补充要求**：在 Panel 中继续输入引导；以界面实际接纳状态为准。
- **停止任务**：使用 Panel 的 Stop。长时间执行的 HOM 操作可能需要等待执行边界，停止不代表撤销已完成修改。
- **程序设置**：启动器右上角“设置”可查看或调整程序路径。
- **版本与诊断**：右上角“诊断”可核对版本、实际数据位置，并导出诊断 ZIP。

## 文件一览

| 文件 | 用途 |
| --- | --- |
| [Installer.exe](Installer.exe) | Windows 安装器 |
| **README.md** | 安装和日常使用入口 |
| [验收指南.md](验收指南.md) | 专用测试步骤与结果记录 |
| [问题反馈.md](问题反馈.md) | 故障处理和反馈模板 |
| [SHA256.txt](SHA256.txt) | 安装器完整性校验值，供需要时核对 |

日常安装和使用无需手动计算校验值。安装包尚未数字签名；若 Windows 阻止安装，请保留提示并按[问题反馈](问题反馈.md)记录现象。

## 数据与升级

安装版默认将持久数据保存至 `%LOCALAPPDATA%\BigChickenStudio\state`，缓存位于同级 `cache`；实际位置以“诊断”为准。

升级前正常关闭会话。卸载保留认证、历史和用户作品。缓存也可能包含未保存作品，遇到问题时请先导出诊断，不要通过清空目录尝试修复。

## 版本信息

| 项目 | 当前版本 |
| --- | --- |
| Build | `0.1.0-rc.1-e6beb5af2de4` |
| 源提交 | [`e6beb5a`](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/commit/e6beb5af2de46ec27b9bc50de068277db38bfe41) |
| 文档修订 | `README-3` · 2026-09-11 |
| 交付状态 | RC 候选；独立标准用户完整验收仍待完成 |

本次候选修正通过 Studio 启动后内置帮助空白的问题，并保留自定义 Houdini 搜索路径、场景产物目录规则及既有启动器界面。验收记录只填写实际结果，未测试的项目不视为通过。

[项目主页](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio) · [验收指南](验收指南.md) · [问题反馈](问题反馈.md)
