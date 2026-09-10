# 审批结论

**批准 Launcher 定稿为「固定节点流 Launcher」：以 `Account → Project 分支 → Launch` 组织操作，以你提供的 Comfy Desktop 截图确定视觉气质。**

这不是给现有按钮换皮，也不是做一个可编辑节点网络。**真正的产品变化是：先选择场景来源，再从唯一的 Launch 节点启动；账号、目标和启动状态在同一个界面里形成清楚的路径。**

本轮的三项基础保持不变：

**正式入口是 `Studio.exe`；正常使用沿用用户自己的 Houdini 配置；Owner 直接使用开发项目中的 EXE，不再额外安装一份 Studio。**附件已将它们确定为前提，而不是待讨论方案。

下面五部分同时构成本轮产品审批和 Codex 施工规格。

---

# 1. Cleanup / Delivery Review

## 当前版本已经核对清楚

| 项目                 | 本次读取结果                                                             |
| ------------------ | ------------------------------------------------------------------ |
| `main`             | `b48ceae62fd1e85f2543f774bfb0f37771f89730`                         |
| PR #14             | Open、Draft，尚未合并                                                    |
| PR head            | **`90a625d821db94a1ceb97465d70541e0dbb24f52`**                     |
| 当前交付 RC            | **`0.1.0-rc.1-4e9db5dec1d7`**                                      |
| Source / builder   | `4e9db5dec1d7c385314262332d0824c5afa0babb`                         |
| Installer SHA-256  | `d6a5d23f96023107902815a784d5e164a071e4897ace236ae5093d0d8176fed5` |
| Tester ZIP SHA-256 | `4b236bc87f7b52309e0b2f579d147a6faab0fb47a72bb20c13de0465838fb73f` |

当前 head 的 CI 已成功。五文件 ZIP 已生成、解压校验，内部 installer hash 与当前候选一致；不是只有打包计划。

我核对了源码与版本化证据，没有操作 Owner 文件、运行 Houdini 或重新计算本地 ZIP 的 hash。

## 已经正确

**入口统一已经落实。**开发与安装布局共用 `Studio.exe`，根据实际根目录选择内部 Python bootstrap；安装器的开始菜单也改为指向 EXE。旧 VBS 用户入口已移除。

**Houdini preferences 的已确认错误已经修正。**正常启动不再强制进入 Studio 独立偏好目录，并保留既有 `HOUDINI_USER_PREF_DIR`；明确的测试环境继续隔离。相关旧失败／新通过回归已经记录。

**交付与历史候选已分开。**旧四文件 handoff 和不含 preferences 修正的中间包已归档；当前五文件 ZIP 不包含开发历史与内部证据。当前交付位置在 Owner 选择的开发盘，不应再改回此前建议的桌面或 C 盘安装方案。

## 仍需收口，但不用重新清理一遍

**第一，正常 Houdini 界面的配置恢复还差实际确认。**当前证据证明生成的启动环境与 `hconfig` 指向原偏好目录，但文档明确写着：实际 desktop、配色恢复等待 Owner 下一次正常启动确认。不能把路径测试扩大为“所有用户自定义配置都已经肉眼验证”。

这次 Launcher 实测时顺带完成：从开发项目的 `Studio.exe` 正常启动，确认原布局、配色、快捷键和实际配置路径。**不复制配置，也不为了让测试通过临时切回默认配置。**

**第二，部分临时副本仍未清除。**PR 记录了清理命令被审批拦截，未执行成功。这些副本不能标为“已删除”，也不要换一种命令绕过限制。只要不再作为活跃入口、不混入 Tester ZIP，就不是 Launcher 施工的阻塞项。

**第三，当前验证文档同时保留多个历史候选。**保留历史正确，但在顶部放一个明确的“当前候选”摘要，其他部分标为历史，不再新增另一份互相冲突的“最终版本说明”。

## 不得再改

不移动开发项目，不再给 Owner 安装产品副本，不恢复 VBS／PYW 用户入口，不迁移 native cwd、认证、历史或 receipts，不整理用户无关目录。

**清理已经足以收口。接下来只做与新 Launcher 交付有关的候选更新，不为目录美观继续搬文件。**

---

# 2. Launcher Product Decision

## 2.1 最终布局：品牌在上，横向节点流在下

**宽窗口采用三列，不采用三张等大的传统卡片横排。**

| 区域   | 定稿                                      |
| ---- | --------------------------------------- |
| 顶部   | 轻量 toolbar，保留原生 Windows 标题栏             |
| Hero | 居中的 `Chicken`，下方一行 creator credit       |
| 左列   | **Account source node**                 |
| 中列   | **Project 分支组**，从上到下为 Empty、Open、Recent |
| 右列   | **Launch sink node**                    |
| 连接   | Account 输出分成三路，各分支输出再汇入 Launch          |

Account 和 Launch 在垂直方向上对齐中间分支组的中心。Project 是一个小标题和分线区域，**不是再加一张没有操作价值的“Project 总卡片”**。

总计五张功能节点：Account、Empty、Open、Recent、Launch。

建议默认窗口 **1120×760 逻辑像素**，主内容最大宽约 1000；Account 约 220，Project 分支约 264，Launch 约 280，两侧留专用连线通道。尺寸可随文字测量微调，但列关系、分支顺序和 source/sink 不变。

这比当前 760×560 的居中阶段页更适合新信息结构。当前实现确实仍是 `QStackedWidget` 阶段页、Home Recent 列表和右上角独立 ellipsis，而不是 node-flow。

### 窄窗口

客户区宽度不足约 980 时，改为紧凑纵向排布：

**Account 在上，三个分支纵向排列，Launch 在下；左右分别保留分流与汇流线道。**

它仍是三条可选路径，不画成 Empty → Open → Recent 的串行步骤。

保留原有 **600×480 最小窗口能力**。小尺寸允许普通垂直滚动，不允许横向溢出、缩小成难读文字或增加 graph pan/zoom。默认尺寸应能同时看见主要节点与 Launch；窄窗口通过正常滚动和键盘聚焦到达全部控件。

不做第三套移动端布局，不建设 responsive layout framework。

---

## 2.2 最重要的交互决定：选择目标，不等于启动

当前 `choose_hip()`、Empty 和 Recent 激活都会进入 `activate_target()`；后者立即创建 request ID 并准备启动。**这个行为需要明确调整，否则 Launch sink 只是摆设。**

新规则如下：

| 操作                      | 新行为                                 |
| ----------------------- | ----------------------------------- |
| 单击 Empty                | 选定空场景目标，激活 Empty 分支，不启动             |
| 单击 Open                 | 打开原生文件对话框；选定文件后更新 Open 与 Launch，不启动 |
| 取消文件对话框                 | 保留此前目标和分支                           |
| 单击 Recent 条目            | 选定该文件，激活 Recent 分支，不启动              |
| 双击／Enter 激活 Recent      | 同样只确认选择，可把焦点移向 Launch，不直接启动         |
| 拖入一个合法 HIP              | 作为 Open 来源选择目标，不直接启动                |
| 点击 Launch 主操作           | 唯一进入现有启动接纳流程的位置                     |
| 登录完成、probe 完成、窗口 resize | 只更新显示，不自动启动                         |

这是本轮**有意改变的 UI 激活语义**，不是要保留旧操作再叠一颗重复按钮。

因此，旧 PR #5 中“选择文件即启动”“Home 不保留全局 Launch”“独立 Launching 页面”的规定，在 Launcher 部分由本轮规格替代。**原有启动身份、进程所有权和未知结果处理仍然保留。**

本轮不创建新的 Project 数据模型。这里的 Project 指**场景入口**，仍使用现有 Empty/HIP `SceneTarget`，不是另建工作区数据库。

---

## 2.3 Account source node

默认展示：

* `ACCOUNT` 小标题；
* 当前账号的一个简短标识；
* 账号确认状态；
* Codex ready／不可用状态；
* 仅在需要时出现下一步操作。

账号与 Codex 是两个事实：**登录成功不能掩盖 Codex 不可用，Codex 初始化成功也不代表账号已登录。**

| 状态                | 展示与动作                       |
| ----------------- | --------------------------- |
| 正在检查              | 轻量 Checking，不先闪出“未登录”       |
| 明确 signed out     | “需要登录”；主操作“使用 ChatGPT 继续”   |
| 登录进行中             | “请在浏览器中完成登录”；保留重新打开与取消      |
| 查询失败／账号结果未知       | “暂时无法确认账号”；查询原状态，不假装登出      |
| 账号确认且 Codex ready | 简短 Ready；不显示一整套成功 checklist |
| Codex 缺失／不兼容      | 在此说明并提供现有修复／选择入口            |

不展示 token、完整套餐详情、配额表或一排状态徽章。

**允许在未登录时选择本地场景。**这是有限的本地选择，不启动 Houdini、不创建 workspace；这样用户无需等账号检查结束才整理目标。Account 尚未满足时，Launch 仍不可执行。

---

## 2.4 Project 分支

### Empty

小标题 `EMPTY`，主文案“空场景”，辅助文案“从新的 Houdini 场景开始”。

整个选择区域可点击、可通过键盘选择。不要把它做成粉色巨型加号按钮。

### Open

小标题 `OPEN`，主动作“选择 HIP…”。

选定后显示文件名，目录在次级行中间省略，完整路径可查看／复制。支持现有 `.hip`、`.hiplc`、`.hipnc`，不改变文件格式政策。

Open 的选择验证可以使用现有只读目标解析；**不能在选择阶段调用 `SceneCatalog.admit()` 或准备启动服务。**

### Recent

小标题 `RECENT`，默认显示**三项**，不是整个文件浏览器。

文件名为主，目录或时间为次；同名文件必须能分辨目录。底部保留“查看全部”。

“查看全部”打开**锚定 Recent 节点的紧凑弹层**，复用现有 Recent 数据与操作；不切换到新的全屏 Recent 页面，不新增搜索平台。

保留重新定位、复制路径、在资源管理器显示、从最近列表移除。移除只影响列表，不删除 HIP、workspace 或历史。当前实现已经提供这些能力，应复用而不是重做。

**键盘焦点不是用户选择，自动聚焦第一行也不能自动激活 Recent 分支。**初次进入不偷偷选择“最近第一项”。

---

## 2.5 Launch sink

Launch 是结果摘要和执行位置，不是另一张菜单。

默认包含：

```text
LAUNCH
当前目标文件名／空场景
已选择的 Houdini 版本与兼容状态
当前 readiness 或阻碍
主操作
```

Ready 必须同时满足账号、Codex、目标与现有 Houdini 启动条件；不是“卡片已经选中”就变绿。

| 状态                  | Sink 行为                               |
| ------------------- | ------------------------------------- |
| 没有目标                | “请选择场景来源”；启动不可用                       |
| 未登录／账号未知            | 保留目标，指出缺失条件                           |
| Houdini 缺失          | “选择 Houdini”；调用既有选择入口                 |
| Untested            | 显示 Untested，主操作“确认并启动”；复用现有绑定到本次请求的确认 |
| Ready               | 显示目标与版本，主操作“启动 Houdini”               |
| Preparing／Launching | 冻结本次目标与路径，显示实际阶段                      |
| Runtime 已连接但目标未确认   | 明确“已连接，正在确认场景”，不能提前显示 Opened          |
| 结果 Unknown          | 主动作“查询启动状态”，继续查询同一 request ID         |
| 已知未启动／进程已关闭的失败      | 显示原因，允许明确的新启动                         |
| 目标确认打开              | Opened，保留既有成功后最小化偏好                   |

**已有可能创建进程的请求时，Launch 状态始终优先。**后台账号状态变化不能让界面重新提供一个会重复启动的按钮。

启动过程中保留 graph，不跳回大面积空白的进度页；其他节点变为只读，所选路径仍可辨认。该请求的准备条件是历史事实，不能因为 Onboarding 正常结束，就把 source 错画成“账号刚退出”。

当前的 request ID、prepare、launch、query、场景确认和 minimize 机制已经存在，本轮只重新投影到节点里。

---

## 2.6 连线与状态语义

**只亮一条选中分支，不是整张图一起变粉。**

未选择的线路低对比；选中分支显示柔和粉色。Account 或目标条件未满足时，路径仍可表示“我选了什么”，但保持较弱，并以文字说明受阻；不能通过亮线伪造 Ready。

Launching 只在已选路径和 sink 表达活动，其他路径不能点击改变已接纳请求。未知结果用静态 warning 和查询入口，不无限流动暗示仍在正常前进。

Ports 是状态锚点，不可拖拽、不可连接、不进入键盘 tab 顺序。颜色之外，还要有选中样式与文字状态，不能完全依赖色觉。

---

## 2.7 Toolbar 和 secondary actions

**取消当前右上独立三点描边框，不只是换一个图标。**

顶部 client toolbar 高约 44 逻辑像素：

左侧小号正式名称 **Big-Chicken Studio**；右侧只有两个平面的次级入口：

**设置**：既有 `settings` 图标加小字。
**诊断**：文字入口，不新增图标。

默认透明、无外框；hover 才出现轻微 surface，键盘 focus 清楚。Account 详情从 Account 节点进入，避免顶栏再重复一个登录入口。

Settings、Account、Diagnostics 继续复用现有次级页面与返回逻辑。返回后保留已选目标和进行中的启动事实，不重新 probe、不重建 Onboarding。

原生标题栏、拖动、最小化、关闭继续交给 Windows，不模仿参考图自绘系统按钮。

---

# 3. Launcher Visual Direction

## 3.1 从参考图取什么，不取什么

参考图最值得吸收的是：**偏紫的暗色背景、弱环境光、低起伏卡片、轻顶栏，以及有性格但不夸张的中心品牌字。**

不复制 Comfy 的实例卡片、云服务、搜索栏、酸黄绿色品牌色或具体字形。Studio 没有这些产品语义，就不为了像参考图而加入。

最终视觉应该是：

> **Comfy Desktop 的克制气质，Houdini 的节点语义，Big-Chicken 自己的品牌和操作结构。**

---

## 3.2 `Chicken`：明确批准一款字体，不让 Codex临场挑选

**使用 `Changa One Italic` 排 `Chicken`，大小写固定为首字母大写。**

选择方向是紧凑、厚实、带圆弧细节和自然前倾的 display 字，而不是系统 Sans Serif 加粗。Google Fonts 的正式 metadata 提供该 italic 字体文件，并将其标为 display/OFL；其设计说明也明确强调短升降部、紧凑轮廓与带曲率的内部形状。

规格定为：

| 项目   | 规格                                        |
| ---- | ----------------------------------------- |
| 字体   | **Changa One Italic，真实 italic 字体，不做人工斜切** |
| 内容   | `Chicken`                                 |
| 正常大小 | 约 44 pt                                   |
| 紧凑大小 | 约 34–36 pt                                |
| 字距   | 先用字体自身 kerning，最多轻微收紧；不拉宽、不挤压             |
| 颜色   | 现有 restrained pink `#EFA2BD`              |
| 效果   | 无描边、无投影、无发光、无渐变填充                         |
| 边界   | 为 italic overhang 留白，不能裁掉 C 或 n 的边缘       |

**本轮明确批准新增这一款仅用于 hero 的字体资源。**它不改变正文、Panel、Houdini 或系统字体，也不意味着新增正式图标或手绘 Logo。

Codex 从官方来源取得资源，固定版本／hash，保留许可证，不修改字形、不改字体名称。字体本地随包，启动时不联网下载。Qt 提供 application-local font loading，足够完成这件事，无需系统字体安装。([Qt文档][1])

字体资源异常时可以用现有字体保住功能，但**正式候选的视觉验收必须证明指定字体确实加载**，不能把 fallback 截图当设计通过。

### 作者署名

放在 `Chicken` 正下方，间距约 6：

```text
bilibili  Chicken-houdini
```

使用现有正文家族，约 9 pt、muted 颜色，居中。不是按钮、不是广告、不加 bilibili Logo，不凭空绑定未确认的主页 URL。

Hero 整块占首屏上部约五分之一，不做占掉半屏的巨型字标。

---

## 3.3 色彩与背景

**Launcher-only tokens，不改共享 Panel palette。**

| 层               | 定稿起点                    |
| --------------- | ----------------------- |
| 主背景             | `#211C27`，偏紫的深灰，不用纯黑    |
| 节点 surface      | `#2B2531`               |
| Hover surface   | `#322A39`               |
| 弱边界             | `#3B3342`               |
| 主要文字            | 沿用 `#F4F4F6`            |
| 次级文字            | 沿用 `#C3C5CE`            |
| Muted           | 沿用 `#989CAA`，不为了高级感降到难读 |
| Accent          | 沿用 `#EFA2BD`            |
| Warning / error | 沿用现有语义颜色，不另建一套          |

当前 pink、文字与状态 tokens 已在 `theme.py` 集中定义，可复用其语义，Launcher 的背景与 surface 用局部覆盖。

背景只加入**一至两处很弱的静态 radial ambient illumination**：hero 后方略偏紫，主路径附近略偏暖粉。不要明显光束，不模拟 Bloom。

**本轮不加网格、点阵或噪声贴图。**节点和连线已经提供足够的 Houdini 识别度，不需要用第三层装饰强化到像编辑器。

---

## 3.4 Node component

节点统一使用：

**10 逻辑像素圆角、16–20 内边距、始终预留的细边界、弱 surface 分离。**不加厚阴影，不做玻璃模糊，不让卡片明显悬浮。

文字层级：

| 内容                                         | 建议                           |
| ------------------------------------------ | ---------------------------- |
| `ACCOUNT / EMPTY / OPEN / RECENT / LAUNCH` | 约 9 pt，小字距，muted             |
| 节点主标题／目标名                                  | 约 12.5–13 pt，medium/semibold |
| 正文／状态说明                                    | 现有约 11 pt                    |
| 路径／时间等次级信息                                 | 约 9.5–10 pt，必要内容不可被压成极小字     |

Empty/Open 节点紧凑；Recent 因包含三项自然更高，不强迫五张节点等高。

选中状态用淡粉 surface 和约 1 像素克制边线；键盘焦点用更明确的 focus ring，**与 selected 分开**。未选择不是 disabled，文字仍可读。真正 disabled 的动作保留原因，不把整张节点压成一块黑灰。

---

## 3.5 Connectors、hover 和动画

线路使用平滑 Bézier，转弯自然，不能穿过节点正文。

* 未选线路：约 1 像素、低对比 neutral。
* 已选路径：约 1.5 像素、柔和粉色。
* Ports：约 6 像素的小圆点，内外状态克制。
* 线条只承担拓扑与选择，不显示“CPU 数据流”“粒子速度”等假信息。

**第一版只保留 120–160 ms 的 hover／selection 过渡。Launching 使用一个既有小型 activity indicator 即可，不必再做无限流动连线。**

这满足状态解释，不为装饰持续 repaint。窗口隐藏或最小化后停止装饰性动画，但保留必要的原请求状态确认。

禁止赛博朋克、强 Glow、渐变主按钮、粗描边、游戏 Launcher、Web dashboard 和花哨 graph。这些不是 Codex 可以自行探索的备选风格。

---

# 4. Release Impact

## 这次必须生成新 RC 和新 Tester ZIP

这不是单纯文档或截图调整。Launcher 的 UI、交互、资源都发生变化，当前 `4e9db5dec1d7` 不能代表新代码。

正确顺序：

**实现 → native preview／截图 → 针对性测试 → 提交候选 → 新 build ID／installer → 包内验证 → 新 Tester ZIP → 候选 CI 与证据收口。**

CI 可以与构建验证并行，但交付的 source、builder、资源与 hash 必须对应。旧候选保留，不改名冒充新包。

## 必须重验什么

| 范围            | 必须验证                                                        |
| ------------- | ----------------------------------------------------------- |
| 选择与启动         | Empty/Open/Recent/拖入只选目标；只有 Launch 接纳；双击不重复启动               |
| 竞态            | 选 A 后选 B，A 的迟到验证不能覆盖 B；账号失效、设置改变、文件消失时不误启                   |
| 原有启动语义        | Untested 确认、request identity、unknown 查询、Runtime/场景确认、成功后最小化 |
| UI            | 宽／窄布局、中文和长路径、keyboard focus、Recent 弹层、字体真实加载、无连线压字          |
| 原 preferences | Owner 从开发 `Studio.exe` 正常启动，沿用原布局／配色／配置路径                   |
| EXE 与包        | 开发 EXE、包内 EXE、安装器开始菜单目标、bootstrap 位置保持                      |
| 数据与交付         | 数据根不变；五文件 ZIP 干净，解压后的 installer hash 一致                     |

真实 Launcher 验证不能仅由 offscreen screenshot 替代；截图也不能只由 mock HTML 替代 native Qt。

## 可以保留什么旧 evidence

NET-1、steer、Tool Capability、staged receipt、旧模型任务与包所有权测试继续保留为其实际版本的证据。**不重新跑完整 TC1/TC2/TC3 benchmark，也不因美化要求模型多做工具调用。**

但新入口的完整登录→选择→启动、正常 preferences，以及新包的 UI/资源加载，需要对应新 candidate 的证据。

## 当前还有什么真正挡住发行

没有从本次审查中发现新的 Tool/Runtime blocker。现在需要完成的是：

**新 Launcher 的功能与视觉验收、原 preferences 的正常启动确认、对应新包交付，以及真实同学的标准用户链路。**

通过新包的技术验证后即可定向发给同学。外测通过且没有新的真实 blocker，再 Ready → merge → public RC；不再附加另一轮全面能力建设。

---

# 5. Codex Final Launcher Execution Brief

以下可以原样交给 Codex。

## Role / Branch / 基线

```text
Pro = 最终产品审批、风险判断和方向。
Codex = 真正 implementation、cleanup、packaging、
        tests、Houdini validation、commit、push、PR。

执行本规格，不再提交另一套 Launcher 设计提案。
```

继续使用：

```text
Branch: codex/windows-release-package
PR: #14

Reviewed head:
90a625d821db94a1ceb97465d70541e0dbb24f52

Current delivery baseline:
0.1.0-rc.1-4e9db5dec1d7

Source / builder:
4e9db5dec1d7c385314262332d0824c5afa0babb
```

开始前核对最新 head，保留无关变更与旧 evidence。若仓库已前进，先检查相关差异，不机械恢复到旧基线。

本轮仅修改 Launcher、其必要资源、测试和交付记录。Panel、Tool Surface、模型指令、Bridge/Runtime 架构、网络政策和动态背景冻结。

---

## A. 三项固定 Owner constraints

**开发和安装产品入口均为 `Studio.exe`。**开始菜单指向 EXE；VBS 已移除，内部 Python bootstrap 不重新出现在用户说明里。

**正常启动沿用用户自己的 Houdini 配置。**保留默认偏好和已有自定义偏好路径；不复制、迁移、覆盖 desktop、color、hotkey 或 preference 文件。测试继续用明确隔离环境。

**Owner 使用指定开发项目中的 `Studio.exe`。**不为其在 C 盘再安装 Studio，不为了模拟外部用户更改本机工作方式。Installer 专供外部用户和明确的安装验收。

开发数据根与外部安装数据根可以按现有模式不同，但必须显示真实身份，不自动迁移或合并。

---

## B. Cleanup 只做最后核对

读取当前本地 inventory 和 Delivery 目录，确认：

```text
Owner EXE 入口唯一明确
当前 RC / Tester ZIP 身份一致
旧活动交付包已归档
历史 evidence 不在用户 ZIP
没有活跃的重复 Studio package
用户数据与源码仍在原位置
```

已有安全归档不重做。之前被审批拦截的临时副本保持“未清除”，不换命令绕过，不谎报删除；只要不作为活跃入口、不进入包即可暂留。

不确定归属的文件不动。不要为了匹配本 Brief 重新设计目录树。

最终产物继续放在 **Owner 已选择开发项目的既有 Delivery 位置**。返回真实 Windows 绝对路径，不要求用户去多个 worktree 里找。

---

## C. Launcher 固定节点流

### 布局

默认约 **1120×760 逻辑像素**，保留原生标题栏和 `Big-Chicken Studio` 标题。

客户端：

```text
轻 toolbar
Chicken hero + creator credit
左 Account → 中 Project 三分支 → 右 Launch
```

Project 中列从上到下为 Empty、Open、Recent。Account 和 Launch 对齐分支组中心。五张功能节点，Project 是标题和分线区域，不造第六张空节点。

宽度不足约 980 时，变为纵向紧凑布局，保留左右分流／汇流线道。最小 600×480，使用普通垂直滚动；无 graph pan、zoom 或拖节点。

不要让新窗口超出当前屏幕 available geometry。默认尺寸不足时用紧凑布局，不强制用户提高屏幕分辨率。

### 选择 contract

增加或复用一个小型 transient selection：

```text
source_branch: empty / open / recent / none
selected_target: 现有 SceneTarget 或 none
selection_generation
selection validity / message
```

不持久化 graph，不增加 Project 数据库。

Empty、文件选择、Recent 行、拖入 HIP 只更新 selection。取消文件对话框保留旧目标。键盘 focus、Recent 自动聚焦、probe、登录成功和 resize 不产生选择或启动副作用。

只有 Launch 激活才创建 request ID，并进入现有 `activate_target → prepare_launch → launch_target` 路径。旧 double-click／itemActivated／行内打开／drop 回调必须一并调整，不能遗留旁路启动。

可以在 signed-out 状态选择本地目标，但 Launch 必须遵守真实 readiness。活动启动请求存在时冻结目标，不接受隐式下一次启动。

选择验证的迟到结果必须按 generation 丢弃；不要让 A 文件的 callback 覆盖后来选择的 B。

---

## D. 节点与状态

### Account

显示简短账号标识、账号确认状态、Codex 状态和必要动作。登录继续使用系统浏览器与已有 Onboarding，不新增认证框架。

Unknown 不等于 signed out。普通成功状态不 dump prerequisite checklist。

### Project

Empty/Open 紧凑，Recent 默认三项。View all 使用锚定 Recent 的原生弹层，复用当前最多 20 项的读取，不新建全屏文件浏览器。

保留 missing file、重新定位、复制路径、资源管理器显示和列表移除。移除不删除用户文件。

### Launch

包含目标、已选择 Houdini、兼容状态、实际状态和唯一主操作。

状态必须覆盖：

```text
Waiting for project
Waiting for account / Codex / Houdini
Ready
Untested confirmation
Preparing / Launching
Runtime connected, scene unconfirmed
Unknown
Rejected / closed failure
Opened
```

Untested 继续复用现有 request/path/version 绑定确认。Unknown 只查原请求，不允许创建新启动。只有确认不存在旧进程影响的失败，才允许用户明确重新启动。

启动后保留 graph 及已选路径，不跳独立进度大页。成功最小化继续要求 Runtime 与目标确认及必要试用确认；进入设置／诊断不能丢失请求或误触发最小化。

已接纳 request 的准备事实与“此刻能否启动另一个请求”分开，不因 Onboarding 正常关闭而错误显示账号退出。

---

## E. Toolbar / secondary pages

移除右上孤立的 ellipsis 方框及其默认外框表现。

顶部右侧：

```text
settings 图标 + 设置
诊断（文字）
```

透明、低对比、平面按钮；hover 局部增强，keyboard focus 明确。Account 管理从 Account 节点进入。

复用现有 Settings、Account、Diagnostics 和返回逻辑，不更改账号、路径选择、导出或恢复后端。

本次批准覆盖旧 specification 中的 Launcher 页面结构、直接激活语义、ellipsis 顶栏和 hero 字体限制；**其他不相关约束不变**。在正式 specification 中记录这项覆盖，不能删除历史审批来掩盖变更。

---

## F. Visual specification

### Hero

```text
Chicken
bilibili  Chicken-houdini
```

`Chicken` 固定使用 **Changa One Italic**，正常约 44 pt，紧凑约 34–36 pt，颜色 `#EFA2BD`。不 fake bold、不人工 skew、不描边、不 Glow、不拉伸。

官方字体来源使用 Google Fonts 的 `ofl/changaone`；记录固定 source revision、文件 hash 与许可证。只引入实际使用的 italic face，离线随包，在 Launcher 进程中加载一次。不要全局安装字体，不改变 Panel／Houdini 字体。

creator credit 使用现有正文家族，约 9 pt、muted，居中放在 hero 下方。不加图标、不做广告卡、不猜作者主页链接。

### Launcher-only 色彩

```text
background       #211C27
surface          #2B2531
hover surface    #322A39
subtle border    #3B3342
primary text     #F4F4F6
secondary text   #C3C5CE
muted text       #989CAA
accent           #EFA2BD
```

现有 success/warning/error 语义色保留。不要修改共享 theme token 造成 Panel 变化；使用 Launcher root 范围的局部样式。

背景仅静态、很弱的 violet/pink radial illumination。无网格、点阵、纹理生成、Bloom 或动态 artwork。

### 节点

约 10 px 圆角、16–20 px padding、细弱边界。状态布局提前预留空间，避免 Ready/Loading 变化让整个 graph 抖动。

category 约 9 pt；标题约 12.5–13 pt；正文约 11 pt。辅助文字不小到不可读。长路径保留完整源值，显示可省略，tooltip/复制可取得完整内容。

选中淡粉 surface，克制边线；focus 与 selection 分开；disabled 说明原因。不能把所有节点涂成粉色。

### 线与动画

未选线约 1 px neutral，已选线约 1.5 px restrained pink，ports 约 6 px。线只经过预留通道，不盖正文。

只保留短 hover/selection 过渡。Launching 使用一个既有 loader；不实现无限流动线、粒子或脉冲网络。

Approved Lucide 0.468.0 资产继续使用，具体可复用 `settings`、`folder-open`、`file-plus-2`、`check`、warning 与 loader 等既有资产。不得换 icon family、自绘功能图标或用 emoji 代替。

---

## G. 实现方式与性能边界

使用普通 QWidget／Qt layouts 构成五张节点；背景层绘制静态 ambient、ports 和连接线。**QPainter 用于这些几何 UI 元素是本轮明确批准，不等于允许自绘正式图标或 Logo。**

连接使用 `QPainterPath`，根据布局后的实际 port anchors 计算并复用。Qt 已提供 Bézier path 和普通 widget paint/update，不需要额外 graph engine。([Qt文档][2])

允许提取一个小型 `launcher_flow.py` 或等价组件，不建立通用节点框架。展示投影只读现有 snapshot、selection 与 launch record，不直接调用服务。

必须避免：

```text
每次 poll 重建节点
每次状态刷新对整个窗口重新 polish
paintEvent 中发请求或修改布局
高频 zero-timer 重排
全局事件过滤器
整个 graph 的循环 opacity 动画
在 HOM 内 processEvents
```

线条在 resize、布局和相关状态改变时更新；static idle 时没有装饰性定时器。隐藏／最小化停止装饰动画，必要的账号与原启动状态确认维持原有策略，不提高轮询频率。

不新增 GPU runtime、QML/WebEngine、依赖下载或 API 扫描。字体、图形资源全部离线。

保留现有后台任务和 `_generation/_serial` 接纳规则，不让纯展示改造导致 App Server 重启、workspace 创建、账号重新登录或多一次 Houdini tool call。

可使用 Codex 已安装的 `$redesign-existing-projects` 做一次对照审查，优先级为：

**本 Brief → 当前有效 specification → 项目边界 → Skill 通用建议。**

不得以 Skill 为理由改技术栈、字体方案或 node-flow 结构。

---

## H. Tests / preview / real validation

### 针对性测试

验证选择没有副作用、唯一 Launch 入口、快速双击、迟到选择、Open 取消、missing Recent、移除/重新定位、Untested 确认、账号变化、unknown request 不重放、settings 返回保持状态、Opened 后最小化。

保留旧测试中的可靠性断言；只替换已被本轮明确改变的 UI 激活预期。不能为了让旧测试通过，重新保留 Recent 双击直接启动的旁路。

### Native previews

至少提供：

**Ready 空目标、Recent 已选、Open 已选、signed out／登录等待、缺少 Houdini或 Codex、Untested、Launching、Unknown recovery。**

在默认与紧凑布局检查节点、线、长文件名、中文与 focus。DPI 只用当前真实环境及一个缩放档进行针对性确认，不扩成完整跨显示器矩阵。

截图来自真正 Qt widgets。先用同样的参考图对照气质，再检查功能，不生成一张概念图冒充实现完成。

### 真实 Launcher 验证

Owner 从开发项目中的 `Studio.exe` 启动，验证自己的 Houdini desktop／配色／快捷键和自定义 preference 路径仍在；不能安装第二份产品，也不能复制偏好。

测试预览继续隔离，不用真实用户配置做故障注入。

通过新的 node-flow 完成登录、选择 HIP 或 Empty、明确 Launch、Runtime/目标确认、正常关闭和重开。Panel 不改造，只确认能正常使用，不需要重跑复杂算法任务。

---

## I. 新候选、Installer 与 Tester ZIP

Launcher 代码、字体与资源变更必须进入新提交，并生成新的：

```text
source commit
builder commit
build ID
installer SHA-256
tester ZIP SHA-256
```

检查字体资源进入实际安装包和许可证材料，开发与安装 `Studio.exe` 都能找到资源；Start Menu 仍指向 EXE，bootstrap 仍在内部。

最终 ZIP 保持一层目录、五个文件：

```text
Installer.exe
SHA256.txt
开始使用.txt
测试步骤.txt
出现问题怎么办.txt
```

TXT 更新为新的操作方式：**选 Empty/Open/Recent → Launch**。不再写“选完文件立即启动”或旧三点菜单路径。

沿用既有白名单打包，解压复核文件数与 installer hash。保留旧候选和 evidence，当前 Tester 目录只暴露一个明确的最新包。

生产包内正常模块、字体与许可证当然保留；不把 Git/source checkout、测试脚本、账号、receipts 或临时截图额外放进外层 ZIP。

Codex 返回实际 Windows ZIP 路径、build ID、source/builder、hash，以及 preview 和功能验收结果。不能只说“位于某个 worktree”。

---

## J. CI / Git / release gate

语义 commits 可按实际工作组织：

```text
feat(launcher): add fixed account-project-launch node flow
style(launcher): establish Chicken branding and restrained surfaces
test(launcher): verify selection-only branches and launch recovery
build(release): package node-flow launcher and tester handoff
```

不要为凑标题拆提交，也不使用 `final`、`polish2` 等无信息名称。

**新包技术门槛：**针对性测试、candidate CI、真实 Qt 截图、实际 EXE 启动、Owner preferences 确认、包内资源与 ZIP 校验通过。

满足后即可交给真实同学进行标准用户测试。使用其自己的 Windows 账户、Houdini、官方账号和 Clash/端口；不要求 no-proxy，不写死 `1121`。偶发 reconnect 若已恢复且输入、历史、操作都完整，不因次数本身阻止测试。

**Draft → Ready：**对应新包的外部标准用户链路通过，结果与准确 build/hash 关联，无新的真实 blocker。

**Merge / public RC：**通过后按本次条件式批准收口，发布同一份已验收安装器；若发现具体失败，只修该问题并重验受影响部分，不再开启下一轮全面产品建设。

---

**本轮定稿就是：`Chicken` 品牌识别、克制的暗紫与粉色、固定的 Account—Project—Launch 节点流。Codex 完成实现、实测和新 ZIP 后，直接进入同学外测；Panel、Agent 能力和 Dynamic Artwork 不再占用本轮范围。**

[1]: https://doc.qt.io/qt-6.8/qfontdatabase.html?utm_source=chatgpt.com "QFontDatabase Class | Qt GUI 6.8.8"
[2]: https://doc.qt.io/qt-6.8/qpainterpath.html "QPainterPath Class | Qt GUI 6.8.8"
