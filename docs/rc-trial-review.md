# 1. Final Release Audit

## 结论：**批准开始日常 RC 试用和定向同学测试；公开发布仍等待标准用户验收**

**在已经验证的 Windows 11 x64／Houdini FX 22.0.368／随包 Codex 0.153.4 组合下，本次没有发现需要重新打开 NET-1、steer 或 Tool Capability 的新 correctness blocker。**

这次正式区分三个状态：

| 状态                      | 审批                         |
| ----------------------- | -------------------------- |
| 你把 RC 作为主要测试入口，持续进行真实工作 | **可以，先确认实际启动路径、数据根和版本正确**  |
| 把 RC 发给指定同学，取得标准用户验收证据  | **可以，不必等标准用户验收完成才允许发给测试者** |
| 合并 #14 并向公众发布测试版        | **仍需标准用户链路通过及最终 Go**       |

这与附件要求的“冻结 RC → 自己使用 → 同学测试 → 根据结果发布”一致；定向发包是完成验收的方法，不是提前宣布验收通过。

### 当前真实基线

| 项目                         | 核对结果                                                               |
| -------------------------- | ------------------------------------------------------------------ |
| `main`                     | `b48ceae62fd1e85f2543f774bfb0f37771f89730`                         |
| PR #14                     | Open、Draft，未合并                                                     |
| PR head                    | `2f068682abf0555e9fa8b370fa5beec7a610c81a`                         |
| Frozen RC source / builder | `991cbce9c90ef7e18dc9a2349ffc95082c5cb0b6`                         |
| Build ID                   | `0.1.0-rc.1-991cbce9c90e`                                          |
| Installer                  | `Big-Chicken-Studio-0.1.0-rc.1-991cbce9c90e-win-x64.exe`           |
| 已记录 SHA-256                | `6e45d650814808e3b0f83be2256e59001cb6f49d436fbdbe49bc96660af92de9` |
| Candidate CI               | Run `34453948861` 成功                                               |

PR head 后来的变化是记录和证据，没有替换上述 frozen installer。NET-1 的真实包复验、同一 Turn 内两次引导、屋顶结果和 fresh-load 检查均已记录，不能再沿用上一轮“这些功能尚未通过”的结论。

**证据边界：**我核对了仓库源码和版本化证据，没有访问你的 Windows 进程，也没有取得 installer 二进制重新计算 hash。因此，本机旧入口、实际继承环境和安装器现场完整性，仍由 Codex按下文核实，不能把仓库审查写成已完成本机检查。

## Blocker、风险与收口项分开

| 类别               | 事项                                      | 决定                  |
| ---------------- | --------------------------------------- | ------------------- |
| **尚未完成的发布 gate** | 独立标准用户的安装、登录、工作、重开、升级与卸载                | 由同学完成，不伪造，不用开发机检查替代 |
| **需补证，不是已发现故障**  | 无 Clash／无开发代理环境下的实际进程链                  | 补一次有界检查；内部与外部网络分别判定 |
| **Owner 环境风险**   | 旧快捷方式、旧数据根、显式 Codex override、遗留 package | 先清点，再处理；不因此修改通用运行架构 |
| **本轮明确要求的政策收口**  | Houdini exact-build 硬拦截；版本来源与兼容状态展示不足   | 批准一组小修改，完成后冻结新 RC   |
| **非阻断限制**        | 未签名、仅有限平台验证、模型产物需要人工检查、长 HOM 不能即时中断     | 如实记录，不再扩建           |
| **后续改进**         | 新工具、动态背景、updater、广泛兼容矩阵、进一步性能优化         | 冻结                  |

有两点已经可以明确下结论。

**第一，内部通信并没有等待 Clash 替它连接 localhost。**通用 `http.Client` 显式使用 `ProxyHandler({})`；修复后的 Panel HTTP 路径直接连接经过验证的 IPv4 loopback socket，没有代理、DNS 或自动重定向路径。

**第二，当前 Houdini exact pin 是产品策略，不是本次找到的 exact-build 技术必需。**`onboarding.py` 和 `preflight()` 明确写死 `22.0.368`；实际 Runtime 入口使用 HOM、`hdefereval` 和已有 Python/Qt 集成，并未在这些路径中体现必须绑定该 build 的 Studio 编译插件。不能据此保证其他 build 正确，但也不应把“未验证”继续写成“已知不兼容”。

**本轮不再开发新功能。只完成版本政策与身份展示的小收口、Owner 清点和必要验证。当前 `991cbce` 可以先在原验证组合上使用；修改启动政策后，必须换成新 RC 验收。**

---

# 2. Owner Cleanup / Current Test Build

## 唯一推荐入口

**日常只使用安装器创建的开始菜单入口。**

不要把下面任何一个继续当作等价的日常入口：

```text
开发 checkout 中的 Start Studio.vbs
.runtime 中某次解包目录的 Launcher
旧 RC 的快捷方式
手工复制的 Python 启动命令
旧 Houdini package 自动启动项
```

开始菜单保留一个当前入口。桌面快捷方式不是必需；保留时必须指向同一当前版本，而不是另一个独立启动脚本。回滚版本可以保留，但放在明确标识的回滚位置，不和当前版本并列显示成几个相同的 Studio。

## Codex 先做只读清点

输出一页本地 `owner-environment-report`，填入**实际值**：

| 检查对象       | 必须记录                                                         |
| ---------- | ------------------------------------------------------------ |
| Windows    | 实际版本、build、账户类型；不能把非提权管理员账户当标准用户                             |
| 入口         | 开始菜单、桌面、固定项的真实 Target、Arguments、WorkingDirectory             |
| 安装         | 当前安装目录、version directories、manifest、installer hash           |
| 进程         | 当前 Launcher、supervisor、Codex、MCP、Houdini 的可执行路径、父子归属和实际版本    |
| 数据         | 本次实际 `state`、`cache`、`CODEX_HOME`、workspace cwd              |
| 环境         | Studio/Houdini/Python 相关覆盖变量；代理变量只记录必要来源与脱敏状态                |
| Houdini 集成 | 生效的 Studio package、Panel 来源、`studio.__file__`、Qt/Python 模块来源 |
| 用户偏好       | 是否残留 `codex_override`、旧 Houdini 路径或开发数据根                     |

**不要导出完整进程环境。**它可能包含认证、代理凭证和其他应用秘密。

如果你的实际系统仍是 Windows 10，应如实记录：当前 installer 的平台门槛是 Windows 11，不能通过绕过 installer 来声称完成当前支持矩阵验收。

## 清理动作边界

| 对象                           | 批准处理                                                 |
| ---------------------------- | ---------------------------------------------------- |
| 已确认废弃的快捷方式                   | 先保存目标信息，再移出活跃开始菜单／桌面入口；操作可逆                          |
| Dev checkout                 | 原地保留。只将相关快捷方式标明 `DEV`，不移动 checkout 内被历史引用的目录         |
| 旧 RC、失败包、验收材料                | 保留准确版本、hash 与用途；至少保留当前 frozen RC 和一个可用回滚版本           |
| 安装器管理的 version directory     | 不手工挪动、改名或整目录清理，避免破坏卸载记录                              |
| 旧 Studio package             | 仅在证明是重复、废弃的 Studio 项后禁用，并保存原文件；不动 Labs 或其他用户 package |
| 全局环境变量 / PATH                | 只处理确认属于旧 Studio 的项；不删除其他应用的 Python、Codex 或代理配置       |
| 残留进程                         | 先确认归属和未保存工作，正常关闭；不按进程名批量终止                           |
| 锁、session descriptor、receipt | 不因“看起来旧”直接删除；旧状态文件不是活进程证据，也不是可安全重放依据                 |

现有 supervisor 已按自己持有的进程和 workspace execution lock 管理所有权，清理工作不应绕过它。

### 绝不能自动删除或合并

HIP、HDA、native conversation history、receipts、attachments、settings、authentication、未决用户输入、release evidence，以及 cache 中可能存在的未保存场景输出。

**“归档旧开发环境”不等于移动整个 `.runtime`。**native cwd 和工件引用可能仍指向它；目录一移动，文件虽然还在，历史链接却可能失效。

## 数据根最终怎么选

优先复用你已经使用的正式持久目录：

```text
%LOCALAPPDATA%\BigChickenStudio\state
%LOCALAPPDATA%\BigChickenStudio\cache
```

但当前 `AppPaths.for_user()` 会接受明确的 `BCS_DATA_ROOT` / `BCS_CACHE_ROOT` 覆盖，因此必须看实际值，不能只看默认文档。

如果重要旧历史只存在于开发数据根：

**原地保留，单独列出，不自动并库、不复制认证、不重写 native cwd。**切换到哪个数据根必须明确说明影响后再执行。新入口显示不到旧历史，并不意味着旧历史已删除；也不能假装已经完成迁移。

清理结束后的验收很简单：

> 关闭已确认属于 Studio 的旧会话，从唯一推荐入口启动一次；实际进程、模块来源、build ID 和数据根都与报告一致。

---

# 3. Network + Version Policy

## 3.1 Proxy：外部网络遵循用户环境，内部 loopback 强制 direct

### 当前审查结论

**`127.0.0.1:1121` 是你的个人网络环境，不是 Studio 的服务地址或产品要求。**

在已审查的启动、Bridge 和 HTTP 生产路径中，没有发现把该端口注入所有用户的行为。`helper_environment()` 保留宿主代理配置；登录用的 App Server 与正式 Bridge 都通过统一的 `codex_app_server_command()`，在 Windows 上启用原生 `respect_system_proxy`。

固定 Codex 版本的官方实现说明：该模式按目标 URL 处理系统代理/PAC、代理环境变量和直连路径。**Studio 应复用这个原生行为，不自己重新排列外部网络路由，也不把坏代理静默绕成直连。**

### 最终批准规则

| 通信                        | 规则                                           |
| ------------------------- | -------------------------------------------- |
| 官方登录、Codex/OpenAI 服务      | 使用当前用户真实有效的系统与原生 Codex 网络配置                  |
| Launcher / Panel → Bridge | 应用内部强制 direct                                |
| MCP / Bridge → Runtime    | 应用内部强制 direct                                |
| Native Codex ↔ Studio MCP | 保持现有 stdio 与受控子进程环境                          |
| 本地服务 endpoint             | 保留 `127.0.0.1` 动态端口、token 和现有身份校验，不改成开发机固定端口 |

`ProxyHandler({})` 明确关闭自动代理发现；因此内部路径不需要用户配置 `NO_PROXY` 才正确。([Python documentation][1])

**不增加代理设置向导，不要求安装 Clash，不修改全局 `NO_PROXY`，不在每次工具调用前做网络检查。**

### Codex 必须补的实际验证

**环境 A：你当前 Clash 开启的环境。**记录 Launcher → Codex、supervisor → Houdini、App Server → MCP 的实际环境继承与可执行路径，确认没有回归。

**环境 B：无 Clash、无 `1121` listener、无开发代理变量的环境。**在该环境中验证 Launcher、Panel、Bridge、Runtime、MCP 的本地工作链路。

另外用一次受控测试，把大小写代理变量指向不可用地址、不给 loopback 设置代理例外，确认内部请求仍直连。使用测试服务和测试 token，不把真实凭证发送到用于验证的代理端点。

需要检查的变量就是附件列出的大小写组合，包括 `ALL_PROXY` 与 `NO_PROXY`；不要只查 uppercase。

**“关闭 Clash，但 Windows 系统代理仍指向 1121”不是健康的无代理外网环境。**这种情况下外部连接失败应如实归为环境问题；内部通信仍必须正常。不要擅自关闭你当前依赖的代理来执行测试。

外部服务在测试者网络不可达时：

* 本地安装／通信可单独 PASS；
* 官方登录／真实模型工作记为 BLOCKED；
* 整条发行验收尚未 PASS；
* 不因此要求用户改用你的代理，也不把问题伪装成模型任务成功。

---

## 3.2 Codex：随包优先，显式 override 保留，版本精确验证

### 当前行为并非随机 PATH 选择

安装入口已经把 `BCS_CODEX_PATH` 指向当前包内 Codex。没有显式设置覆盖时，PATH 中的新 Codex 不会优先于它。实际需要留意的是：保存的 `codex_override` 可以优先于安装入口注入的路径。

**批准保留这个能力，但明确其产品语义：**

| 场景                                    | 行为                                                    |
| ------------------------------------- | ----------------------------------------------------- |
| 正常安装用户                                | 使用当前 Studio 包内 Codex                                  |
| PATH 中出现 0.154、0.160 或 future version | 不改变 Studio 的选择                                        |
| 用户在高级设置明确指定 external Codex            | 允许，但必须通过当前精确版本和 initialize 检查，并显示 `Explicit external` |
| 旧的自动发现缓存                              | 不应抢占当前 bundled 默认值                                    |
| External override 不兼容或失效              | 明确失败，提供“恢复使用随包版本”；不静默改选另一个外部程序                        |
| Bundled 缺失或损坏                         | 报安装问题并修复安装，不去 PATH 随便找一个顶替                            |

当前精确验证值继续是 **`codex-cli 0.153.4`**。已有 `check_codex()` 会拒绝其他版本，这个边界保留，不改成“最低版本以上都行”。

你的 Owner 清点中，若发现旧开发 `codex_override`，先备份该偏好并显示来源，再恢复 bundled；不必因此重写发现系统。

### 后续升级原则

**Studio release ↔ validated Codex version ↔ App Server contract** 一起更新。

不是每次 Studio 小版本都必须追最新 Codex，也不是永远锁死 0.153.4。需要更新时，在新的 Studio 候选中替换 bundle，并验证 initialize、账号、Thread、start/steer、MCP approval、Stop 和未知结果处理，再发布。

不让 native Codex自行更新当前 immutable 安装目录；不增加自动 updater；不把未验证的新协议交给用户自行碰运气。

---

## 3.3 Houdini：正式采用“已验证／未验证／不支持”

### 本轮批准的政策

| 状态                              | 首个测试版范围                                                        | 行为                                           |
| ------------------------------- | -------------------------------------------------------------- | -------------------------------------------- |
| **Validated**                   | Windows 11 x64，Houdini FX 22.0.368，现有已验证 Python/Qt 组合          | 正常启动                                         |
| **Untested**                    | 其他 Houdini 22.0 build；同代 Core、Indie、Education GUI              | 说明未验证，用户显式确认后允许尝试；启动基础能力检查通过不自动升级为 Validated |
| **Untested，默认不自动选择**            | 后续 Houdini 22.x minor 版本                                       | 仅手动选择并确认后尝试，必须仍满足已有集成前提                      |
| **Unsupported by this release** | 其他 major、无 GUI 的 Engine/MPlay 用法、缺少所需 Python/PySide6/启动接入能力的配置 | 不进入正常 Studio 工作，报告具体原因                       |
| **无法确认**                        | 版本读取失败、许可证尚未确认                                                 | 保持 unknown，不伪装成不支持或已验证                       |

这项政策**替代当前两个位置的 `!= "22.0.368"` 硬拦截**。不是将所有 22.x 宣称为兼容，而是允许用户在知道风险的情况下参与测试。

实施只需要一个共用的小型分类函数，供 Onboarding 和 preflight 复用；不建立兼容数据库或扫描整个 HOM。启动后沿用实际 Runtime/Panel 注册，补读必要的版本、应用和许可证事实；不要额外启动一个 Houdini 进程只为探测。

当前包有 3.10、3.11、3.13 的 UI-ready 接入目录；这只是入口存在，不是三个宿主组合都已验证。若宿主使用未覆盖的 Python 接入方式，必须报告真实失败，不自动安装或替换 Houdini 自带 Python/Qt。

### Edition 结论

**FX 是 Studio 已验证的 edition；Core、Indie、Education 是可进入受控测试的候选，不是已获完整支持认证。**

SideFX 的各类产品共享安装来源，但许可、功能与文件格式不同。Core 的直接 DOP authoring 能力与 FX 不相同；Indie、Education 的保存格式和使用限制也不同。Studio 不应绕过许可，也不能用一个“Commercial”值就断言是 FX。([SideFX][2])

因此：

* 尽量依据实际应用与许可证事实显示 edition；无法明确识别时显示“edition 未确认”。
* 使用用户正常取得的许可证，不偷偷强制换成 FX。
* 保存、打开、导出以实际生成的 `.hip`／`.hiplc`／`.hipnc` 和对应资产格式为准，不能靠改后缀伪装兼容。
* Core、Indie、Education 的试测通过后，只记录确实通过的 edition/build/流程，不顺带认证全部组合。

**测试相邻 build 不是首发前的新矩阵任务。**验证分类与拒绝行为，并确保已验证组合不回归；其他组合仍明确叫 Untested。

---

## 3.4 版本信息：只补缺失的只读事实

当前 diagnostics 已有 Studio version、source commit、Codex/Houdini version，但缺少直接的 `build_id`、程序来源与兼容分类，而且其 Houdini 信息主要来自 Launcher 选择快照。

批准在**现有连接详情／诊断位置**补充：

```text
Studio version / build ID
当前 installation root
Codex 实际路径、版本、Bundled / Explicit external
Houdini 选择的版本与实际连接的版本
Validated / Untested / Unsupported / 尚未确认
当前 state / cache 位置
```

路径可在本地详情中显示；默认 diagnostics ZIP 不因此加入用户名、完整用户路径、代理凭证或环境 dump。导出只增加有限的 build/source/compatibility 标量字段。

**未启动时写“已选择”，已连接后写“正在运行”。**不要把 manifest 的目标版本当成现场探测结果。

这些信息从已有配置和缓存状态取得，不放进每轮模型 context，不增加 tool call，不在每次轮询做全包 hash。

---

## 3.5 Studio 升级、回滚、卸载：冻结现有架构

现有 per-user installer、不可覆盖的版本目录、安装中进程保护与用户数据分离设计继续使用。新包安装后更新正常开始菜单入口，旧版本目录保留；用户数据不随版本目录迁移。

最终规则：

**升级前正常关闭相关 Studio 会话；安装器不强杀 Houdini。**升级后保留 native cwd、conversation、receipts、settings 和附件。

**卸载只移除安装器拥有的程序与入口。**不自动删除 state、认证、历史、HIP/HDA、外部输出，也不把整个 cache 当作可删垃圾。

**回滚允许选择保留的程序版本，但不承诺所有未来数据结构永远向后兼容。**每次正式升级应声明数据兼容性；本轮不做迁移框架，不通过重编号 workspace 来“修复”旧版兼容。

---

# 4. External Tester Package / Acceptance

## 直接发给同学什么

只准备一个清楚的测试包目录：

```text
Big-Chicken Studio 测试包
├── Installer.exe
├── Installer.exe.sha256
├── 开始使用.md
└── 测试结果.md
```

`开始使用.md` 控制为短说明，包含 build ID、支持环境、未签名状态、官方登录、启动方式、数据保留和 Diagnostics 位置。`测试结果.md` 是简短的 PASS／FAIL／BLOCKED 表，不要求测试者阅读源码或分析日志。

**测试者不必手动计算 hash。**保留 sidecar 供传输损坏核对；日常只需要能在 Launcher 中看到本次指定 build ID。

如果只是外置说明和 evidence 更新，不重建 frozen RC。若要把新的兼容策略和版本展示放入产品，则必须发新的 installer，不能继续沿用 `991cbce` 的 hash。

## 环境要求与边界

标准用户 gate 使用 Windows 11 x64 的实际非管理员账户，正常可用的 Houdini 与许可，以及测试者自己的官方账号和网络。

不能要求同学复制你的 Clash、环境变量、认证、Codex、Python 或开发目录。

已安装其他 Python/Node/Git 不需要为了测试卸载，但 Studio 不能依赖它们。没有 Clash 的同学环境可以同时提供环境 B 的证据。

同学使用 Untested Houdini 时可以参与探索测试，但**不能据此替代已声明 Validated 组合的完整外部验收，也不能把局部失败直接宣称整个 Studio 都不兼容。**

## 一条可执行的测试流程

| 步骤             | 测试者操作                                           | PASS 标准                               |
| -------------- | ----------------------------------------------- | ------------------------------------- |
| 1. 安装          | 正常安装，开始菜单打开                                     | 不要求 Python、Node、Git、pip 或开发命令；版本身份正确  |
| 2. 登录与检测       | 选择 Houdini，完成官方登录                               | 程序版本与兼容状态准确；网络失败有可理解提示                |
| 3. 实际工作        | 从空场景做一个可编辑百叶窗，包含窗框和数量／间距／角度控制                   | 实际几何和控件有效，不只是文字宣称完成                   |
| 4. 中途引导        | 工作期间发送“改为十二片，窗框尺寸不要改变”                          | 当前任务接纳引导，输入不丢失；若 Turn 恰好结束，明确未发送并保留草稿 |
| 5. 反馈与续改       | 查看反馈图，再改一个参数                                    | 图像可读，原网络继续编辑，消息完整且错误可见                |
| 6. 保存与重开       | Save As、关闭、从 Launcher 重开并 resume 原 conversation | 文件、历史与结果可访问；还能继续修改                    |
| 7. Stop        | 在较长或分阶段工作中点击 Stop                               | 诚实报告已完成和停止部分，不保证瞬时中断，不重复执行            |
| 8. Diagnostics | 导出 ZIP                                          | 只含白名单信息，无聊天正文、凭证、图片或作品                |
| 9. 升级          | 先在会话活跃时尝试，再正常关闭后升级                              | 活跃保护生效；升级后对话与数据保留                     |
| 10. 卸载／重装      | 正常卸载后重装                                         | 程序可移除，用户数据按说明保留，重装可续作                 |

升级测试可使用保留的上一内部包，不需要为了验收升级再开发一个版本。

### 判定与反馈

**PASS：**预期行为成立，必要文件与截图已保存。

**FAIL：**行为与说明不符，例如错版本启动、消息丢失、误发新 Turn、重复执行或数据被删。

**BLOCKED：**网络、许可或测试环境使该步骤无法进行。不是通过，也不自动认定为 Studio defect。

同学默认只提交：

> **发生了什么、截图、Diagnostics ZIP。**

不要求其判断根因。如果这些材料不足，再由 Codex提出最小、明确授权的补充取证；不要为预防所有未来问题提前扩充日志收集。

---

# 5. Codex Final Release Brief

以下内容可直接交给 Codex。

## Role / 当前基线

```text
Pro = 最终发布审批、风险判断和方向。
Codex = 本机调查、必要修改、tests、真实验证、
        commit、push、PR 和测试包收尾。
```

继续在：

```text
Branch: codex/windows-release-package
PR: #14

Reviewed head:
2f068682abf0555e9fa8b370fa5beec7a610c81a

Existing frozen RC:
0.1.0-rc.1-991cbce9c90e

Source / builder:
991cbce9c90ef7e18dc9a2349ffc95082c5cb0b6

Recorded installer SHA-256:
6e45d650814808e3b0f83be2256e59001cb6f49d436fbdbe49bc96660af92de9
```

本轮允许你先让 Owner 在验证组合下使用当前 RC，并把合适的 RC 发给指定同学验收。**这不是授权在验收前 merge 或公开发布。**

NET-1、same-Turn steer、Tool Surface、staged execution、模型指令、consent、conversation lifecycle、Panel/Launcher 架构冻结，不重复建设。

## A. Owner 环境先调查，后清理

检查真实 Windows build、快捷方式、安装版本、进程树、模块来源、数据根、Studio 环境变量、代理继承与旧 package。

生成一页本地报告，明确：

```text
唯一推荐入口
当前 build ID
实际 bundled / external Codex
实际 Houdini
Studio / Python / Qt 模块来源
state / cache / CODEX_HOME / native cwd
旧入口处理清单
必须保留的旧版本与证据
```

只读取必要字段，不导出凭证。先展示拟处理项目；仅对确认废弃的入口作可逆处理。

不要移动仍被 history/cwd 引用的开发 `.runtime`；不要并库或复制认证；不要以清理为由删除 receipts、未决发送、cache 输出或验收证据。

保持开发 checkout 可用，但从日常入口中清楚隔离。安装器开始菜单是唯一日常推荐入口。

## B. Proxy independence：验证，不重写

保留：

```text
外部服务 → 当前用户的原生 Codex / 系统网络政策
内部服务 → 显式 direct IPv4 loopback
```

检查实际 Launcher、App Server、supervisor、Houdini、MCP 的继承环境，包含大小写 proxy/no_proxy 变量、Windows 系统代理，以及是否有自定义配置把请求指向开发端点。

验证 Clash ON 和无 Clash 环境。另以不可用代理地址和空 no_proxy 做本地通信回归，证明内部请求不靠用户代理例外。

不改全局代理，不强制外网直连，不添加 `1121`，不自动修复用户网络。外网失败与本地失败分开记录。

**若这些测试通过，不修改 HTTP 实现。**只在找到真实错误后做对应局部修正。

## C. Codex precedence：冻结明确策略

正常 installed entry 使用当前包内 Codex。

保留用户在高级设置明确选择的 external override，但只接受 `0.153.4` 并完成现有 initialize 验证。无效 override 明确失败，不静默去 PATH 找其他版本。

PATH 或自动发现缓存不改变正常 bundled 默认值。Owner 的旧 override 通过本机清点处理，不做用户配置自动清扫。

显示实际来源与版本；启动时确认的可执行路径继续传递给正式 Bridge，不能在登录后再次重新发现。

不升级 Codex，不实现 auto-update，不扩大兼容版本范围。

## D. Houdini compatibility：批准唯一的启动政策修改

将 Onboarding 和 preflight 的 exact-build 判断合并为一个小型分类函数：

```text
22.0.368 / 已验证组合：Validated
其他 22 系列 / 满足基础集成前提：Untested，显式确认后尝试
其他 major、无 GUI、缺必要集成能力：Unsupported by this release
无法确认版本或 edition：Unknown，不伪造判断
```

自动发现优先已确认的用户选择和已验证安装；不要因为另一个更新的未验证安装存在，就静默切过去。

确认只影响启动风险告知，不授予额外 HOM 或文件权限。Untested 启动成功仍然是 Untested。

使用实际宿主 Python/Qt，不安装替代库。启动时只读取必要事实，不扫描整个 API，不跑新模型任务来“探测兼容性”。

Core、Indie、Education 允许进入明确标注的试测路径，不宣称完整支持；保留真实许可与文件格式。不能通过 executable basename 或单一 license category 猜测 FX。

## E. 版本 UI / Diagnostics 最小补充

在现有详情区域补足 build ID、Codex 来源、选择与实际运行版本、兼容状态。

本地可显示路径与数据根；Diagnostics 只增加白名单标量，例如：

```text
build_id
codex_source
houdini_compatibility
可取得的实际 application / license category
```

未取得的值为 null/unknown，不拿选中值冒充正在运行。

不新增页面体系、不增加每轮模型 context、不每次工具调用校验版本、不每次轮询 hash 安装包。

## F. Tests 与新 RC

针对性测试必须包含：

| 范围      | 测试                                                                |
| ------- | ----------------------------------------------------------------- |
| Codex   | PATH 中更高版本不抢占 bundle；显式 override 精确验证；无效 override 不静默 fallback    |
| 代理      | 两种生产内部客户端在代理变量存在／缺失／错误时均保持 direct                                 |
| Houdini | Validated/Untested/Unsupported/Unknown 分类一致；显式确认；原 22.0.368 路径不回归 |
| 身份      | selected 与 running 区分；build ID 正确；默认 diagnostics 不泄露路径与凭证         |
| 基本产品链   | 已验证安装上的启动、history、一次 steer、保存重开及数据归属不回归                           |

不要求额外验证一整套 Houdini daily-build 矩阵。mock 的相邻版本分类只能证明政策逻辑，不能写成真实兼容验收。

**本轮批准的 Houdini 政策和身份展示属于产品代码变化，因此实施后必须产生新 RC。**

```text
提交代码
→ candidate CI
→ 新 source/builder identity
→ 新 build ID 与 installer hash
→ 验证受影响范围
→ 冻结新 RC
```

旧 `991cbce` 保留为准确的历史候选与回滚材料，不再被称为包含新政策的最新包。

如果只更新外置 tester instructions、清理报告或 evidence，不重建。若修改的是随包文件且需要把该变化发给用户，就属于 package contents 变化，按新包处理。

## G. 测试包交付与 gate

准备 installer、checksum、短说明和 PASS/FAIL/BLOCKED 表；测试者无需开发工具、手工 MCP 或复制 Owner 环境。

Owner 自用证据与 External tester 证据分开。完成本地环境 B 不能冒充标准用户安装完成；同学网络不可达也不能伪装成整条流程通过。

PR 在外部链路未通过前保持 Draft。可以分发 frozen RC 给指定测试者取得证据，不能将其包装成已认证的公开版本。

**Ready gate：**最终 RC 的本地回归与 CI 通过、Owner 入口清楚、网络依赖检查有结论、同学完整安装链路通过。

**Merge gate：**证据指向准确 installer hash；没有未解决的数据丢失、身份混用、重复执行、错误版本或必要恢复故障；提交最终 Pro Go。

**公开测试版 gate：**发布的就是获批并被验收的那份安装器。不得合并后悄悄重打包替换；支持矩阵、未签名状态与 known limitations 一致。

语义提交按实际内容组织，例如：

```text
fix(compatibility): distinguish untested Houdini builds from unsupported hosts
feat(diagnostics): expose release identity and component provenance
test(release): verify proxy-independent loopback and runtime selection
docs(release): add owner handover and external tester instructions
```

没有发现对应缺陷就不要为了凑提交而修改网络、Runtime 或工具层。

---

## 最后的四个回答

**现在能不能把它当日常 Studio 使用？**
可以开始以 RC 身份作为主要测试入口，前提是确认实际组合与数据根；不等于承诺长期零故障，也不应把未保存的重要作品只留一份。

**没有你的 Clash／开发环境，同学能不能运行？**
内部通信和随包依赖的代码路径没有显示这种必需依赖；实际无代理进程链与安装验收仍需补证，外部 Codex 服务另需测试者可用的网络。

**版本变化时是否可预测？**
Codex 继续精确 pin、默认 bundled、显式 override；Houdini采用明确三态与用户确认；Studio 显式安装升级、程序和数据分离。不是“机器上哪个最新就用哪个”。

**同学通过后是不是就可以发布？**
**是。完成这次有限收口、冻结对应 RC，同学通过后提交最终 Go，然后 merge 和发布。除非发现新的真实 blocker，不再开启下一轮功能建设。**

[1]: https://docs.python.org/3.13/library/urllib.request.html "https://docs.python.org/3.13/library/urllib.request.html"
[2]: https://www.sidefx.com/Support/licensing/ "https://www.sidefx.com/Support/licensing/"
