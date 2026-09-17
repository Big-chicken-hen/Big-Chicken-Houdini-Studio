# Big-Chicken Houdini Studio

在 Houdini 中，通过 Codex 对话创建场景、调整参数，并在原作品上继续修改。

**Release Candidate** · **Windows 11 x64** · **原生 Houdini Panel**

[快速开始](#快速开始) · [环境要求](#环境要求) · [日常使用](#日常使用) · [问题反馈](#问题反馈)

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
| **README.md** | 安装、日常使用、版本和问题反馈说明 |

安装包尚未数字签名；若 Windows 阻止安装，请保留提示并按下方[问题反馈](#问题反馈)记录现象。

## 数据与升级

安装版默认将持久数据保存至 `%LOCALAPPDATA%\BigChickenStudio\state`，缓存位于同级 `cache`；实际位置以“诊断”为准。

升级前正常关闭会话。卸载保留认证、历史和用户作品。缓存也可能包含未保存作品，遇到问题时请先导出诊断，不要通过清空目录尝试修复。

## 问题反馈

启动器能够打开时，点击右上角 **诊断 → 导出诊断…**，保存 Diagnostics ZIP。
默认诊断不包含聊天正文、凭证、图片或作品。如果启动器打不开，先提供 Windows 提示截图和启动位置即可。

```text
Build：0.1.0-rc.1-b6bed7cdac13
Windows / Houdini 版本：
发生位置：启动器 / Panel / 安装过程
发生时间 / 已连续使用时长：
操作步骤：
预期结果：
实际结果 / 完整错误提示：
能否再次复现：
截图 / Diagnostics ZIP：
```

遇到连接异常时，保留原消息、附件和后续草稿，结果未知时不要反复发送。
Clash 继续使用自己的正常配置；不要通过清空账号、历史或缓存尝试修复，也不要发送认证文件、Clash 配置或整个用户目录。

## 版本信息

| 项目 | 当前版本 |
| --- | --- |
| Build | `0.1.0-rc.1-b6bed7cdac13` |
| 源提交 | [`b6bed7c`](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/commit/b6bed7cdac1381765ba221ec8847c0b9a70f5f0e) |
| 文档修订 | `README-4` · 2026-09-17 |
| 交付状态 | RC 候选；独立标准用户完整验收仍待完成 |

本次更新改进连接异常后的输入恢复：明确未发送的请求可恢复原文和附件，结果未知时保持核对，不自动重发。同时保留内置帮助修正、自定义 Houdini 搜索路径、场景产物目录规则及既有启动器界面。

用户已反馈开发入口本轮使用正常；新安装包的真实使用和独立标准用户完整验收仍待完成。流程图代码块目前仍按源码显示，Mermaid 预览未纳入本次更新。验收记录只填写实际结果，未测试的项目不视为通过。

需要核对安装器完整性时，可使用以下 SHA-256（日常使用不必手动计算）：

```text
ceddcb77c7fd3ac16d149ccafe95ec41cf0e0a04951f939505172f1ab4f9a3da  Installer.exe
```

[项目主页](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio) · [返回快速开始](#快速开始)
