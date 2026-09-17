# 2026-09-17 安装包更新

用户明确要求“先不做这个，先把安装包更新一下吧”：Mermaid 继续暂停，本次只把
已经提交的修复更新到交付包。随后用户要求“包内就留一个 readme”，最终 ZIP
仅包含 Installer.exe 和 README.md，安装/使用/反馈/校验信息均在该 README 内。
此授权替代此前保留原 ZIP 的安排，不扩大产品功能。

## 交付身份

- Build：`0.1.0-rc.1-b6bed7cdac13`。
- 源码 / builder：`b6bed7cdac1381765ba221ec8847c0b9a70f5f0e`。
- 当前交付：`发布包/Big-Chicken-Studio-0.1.0-rc.1-b6bed7cdac13-Tester.zip`。
- 外层 README-4，2026-09-17；唯一说明文件与 `release/handoff/README.md` 字节一致。
- 原 `e6beb5a` ZIP 已在新包读回通过后删除，历史身份和验收证据保留。

| 产物 | Bytes | SHA-256 |
| --- | ---: | --- |
| Installer.exe | 216143048 | `ceddcb77c7fd3ac16d149ccafe95ec41cf0e0a04951f939505172f1ab4f9a3da` |
| Tester ZIP | 215691195 | `ddda587374d5e93e047b546a8893a47508af529277a127f5370c989080a391e6` |

机器可读记录：[delivery-b6bed7c.json](evidence/r4-connection/delivery-b6bed7c.json)。

## 本次验证

源候选的 [CI 35051014113](https://github.com/Big-chicken-hen/Big-Chicken-Houdini-Studio/actions/runs/35051014113)
五个作业均通过。构建使用 E 盘临时干净 checkout，未包含日常工作树中既有的
`docs/authoring-results.md` 修改。现成的锁定输入缓存和编译器只读复用；本轮
新增产物均位于 E 盘，没有安装到开发者系统。

- 245 项安装载荷文件哈希全部匹配，没有额外载荷文件；产品源码逐文件与候选一致。
- 实际包内 Python 3.13.15 及 Panel/shared/diagnostics/PySide6 模块执行 24 项
  隔离回归，0 failure、0 error。QtTest 仅从同锁定 wheel 放进外部测试目录，
  未加入发行载荷；测试后的完整清单再次读回匹配。
- 初版五文件 ZIP 已在本轮按用户要求重新整理为两文件 ZIP；安装器字节未变，
  重新读回 CRC、内层安装器 SHA-256 和唯一 README，2 个相对文件链接均可解析。
- 目录中仅保留最新 ZIP 和校验文件。临时源码 checkout、解包载荷、散装安装器、
  QtTest 测试依赖和临时目录已删除；本轮仅保留约 32 KB 的本机验证记录。

## 验证边界

本次没有修改产品代码或 UI，没有安装 Mermaid/浏览器/图表依赖，也没有改变
Clash、Houdini 偏好、环境键名或已有账号/历史/工作空间。新包包括此前已提交的
连接前失败恢复、原消息终态处理和断连退避，并保留已关闭的 HELP-1 修正。

没有运行系统安装器、新包真实 Houdini GUI、模型任务或独立标准用户验收。
开发入口的既有用户复测正常不改写为本包的验收 PASS；包内离屏测试也不替代
真实宿主。`release_acceptance` 继续为 `pending`，安装器仍未签名，PR #14
保持 Draft，不合并或公开发布。10048 现场来源未因本次打包而得到确认。
