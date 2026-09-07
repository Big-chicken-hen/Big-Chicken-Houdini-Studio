# PR #5 approved presentation specification

User-supplied Pro review, 2026-09-06. Review head: 99761e99c94588e4876297992836a78ae8c1596d. The operative specification below is preserved from the review. It supersedes the earlier Dashboard layout and permission to use Qt system icons in product UI. Existing backend contracts remain frozen.

**Current status:** the [later Pro closure approval](pr5-closure-brief.md), reviewed at `06b2c5c`, supersedes this document's construction stages and Merge Gate. UI implementation is frozen; the original text below remains the approved visual specification and a record of the completed construction stage. The current compact gate includes real account continuity, input, model/consent, image-informed editing, Save/Save As/reopen and bounded running-HOM Stop. An untested full cross-monitor DPI matrix alone is not a merge blocker. Only confirmed user-flow defects authorize further PR #5 code changes.

# 第二部分｜我决定的现代产品方向

## 1. Launcher：分阶段、非向导式的 Scene Launcher

最终结构定为：

**Checking → 需要时 Setup → 需要时 Authentication → Ready Home → Launching。**

这不是让每个人每天走一遍向导。**只有实际缺失的阶段才出现。**

Ready Home 不再显示成功 checklist，不再保留全局 Launch Studio 按钮。打开一个目标，就是主要操作。

### 完整页面状态模型

| 页面                           | 进入条件              | 用户当前任务                           | 离开条件           |
| ---------------------------- | ----------------- | -------------------------------- | -------------- |
| **Checking**                 | 初次检查尚未完成          | 等待确认必要条件                         | 得到可解释的检查结果     |
| **Setup：Codex**              | 缺失、不兼容或无法初始化      | 安装／选择有效 Codex                    | 原生检查成功         |
| **Setup：Houdini**            | 没有可用安装            | 选择本机 Houdini                     | 安装路径确认         |
| **Authentication**           | 明确未登录或当前认证方式不适用   | 使用 ChatGPT 登录                    | 原生账号确认成功       |
| **Authentication：Waiting**   | 已发起官方登录           | 在浏览器完成登录                         | 成功、明确失败或取消     |
| **Authentication：Attention** | 账号查询失败／登录操作结果未知   | 查询原状态或处理连接                       | 得到权威账号结论       |
| **Home**                     | 必要环境和账号已确认        | 打开 Recent、Open HIP 或 Start Empty | 用户激活一个目标       |
| **Launching**                | 一个启动意图已进入准备／提交    | 等待目标打开                           | 确认打开、明确失败或结果未知 |
| **Launch Attention**         | 启动可能已经发生但结果未确认    | 查询同一请求                           | 得到终态，不产生第二次启动  |
| **Opened**                   | Runtime 与目标场景均已确认 | 转入 Houdini                       | 默认最小化 Launcher |

Setup 的两个情况使用同一种页面模板，不需要两套平行框架。Authentication 的等待与错误也属于同一页的局部状态。

Settings、Account、Diagnostics 是可返回的次级页面，不参与另一套业务状态机。

### 状态优先级

**已经存在可能启动进程的 request 时，Launch 页面优先。** 后台一次账号检查失败，不能把用户从“启动结果未确认”带回登录页，再允许发起一个新启动。

不存在活跃启动请求时，按：

**Codex → Houdini → 账号 → Home**

决定需要展示的前置问题。检查可以并行或复用现有 probe，但界面一次只要求用户解决一个阻碍。

---

## 2. Returning user：不再展示成功检查表

用户第二天打开 Launcher：

**窗口立即出现；检查静默进行；条件正常则直接进入 Home。**

不强制展示“检查成功”动画，不设置必须观看的最短等待时间。检查超过约 250 毫秒时才显示轻量的 Checking 内容；这只是减少闪烁的展示延迟，不是宣称后端一定能在该时间完成。

不把缓存的“昨天已登录”当成今天已确认，也不在短暂未知时先闪出登录页。

**正常用户看到的是最近文件；只有异常用户才看到 prerequisites。**

---

## 3. 页面变化不应改变后端所有权

采用一个小型页面投影即可：

**现有 readiness snapshot、account facts、launch record → 当前页面及局部状态。**

页面切换不自动启动新 App Server，不重建 onboarding owner，不产生新 launch request，也不改变 scene identity。

**页面状态用于决定“显示什么”，不用于决定“操作事实上是否发生”。**

---

# 第三部分｜Launcher 与 Panel 的具体 UX Specification

以下是本轮确定的产品规格，不再让 Codex自行选择另一种页面模型。

## A. Launcher

### A1. 窗口与导航

默认内容区域约 **760×560 逻辑像素**，最小约 **600×480**。所有阶段使用同一窗口尺寸；认证页不能缩成一个小窗口，登录成功后又突然扩成大窗口。

保留原生窗口标题栏和系统窗口管理。标题为 **Big-Chicken Studio**。

客户端顶部只保留品牌文字与右侧 `ellipsis` 菜单。正常 Home 不常驻“高级”“详情”两个按钮。

菜单按层次组织：

**账号与设置**为次级；**诊断**为第三级。没有正式 Logo，不为文字左侧预留一个必须填图的洞。

---

### A2. Authentication 页面

认证页不显示 Recent、Houdini 列表、Launch、输出目录或技术状态表。

内容居中，最大宽约 360：

**标题：登录以继续**

说明：**使用你的 ChatGPT 账号连接 Codex。**

主要按钮：**使用 ChatGPT 继续**

辅助文字：**登录将在系统浏览器中完成。**

底部次级入口：**遇到问题？查看详情**

不放账号密码输入框，不放自制 OpenAI Logo，不嵌浏览器，不自行管理认证 token。

点击后，同一区域切换为：

**请在浏览器中完成登录**

保留 **重新打开登录页** 和 **取消本次登录**。这里“取消”只取消当前官方登录，不退出应用，也不启动另一轮认证。

成功后重新确认账号；确认成立便进入 Home，**不要求再点一次 Continue**。

如果只是网络检查失败，显示“暂时无法确认账号”和“重新检查”，不能显示“你已退出登录”。现有 `Onboarding` 已区分这些事实，应直接复用。

---

### A3. Setup 页面

Setup 只显示当前需要处理的程序。

| 原因          | 标题              | 主操作        | 次级操作      |
| ----------- | --------------- | ---------- | --------- |
| 未找到 Codex   | 需要 Codex        | 查看安装步骤     | 选择已有安装    |
| 明确版本不兼容     | 当前 Codex 版本不受支持 | 选择兼容安装     | 查看要求      |
| 程序存在但无法初始化  | 无法启动 Codex      | 重新检查       | 选择其他安装、详情 |
| 未找到 Houdini | 需要 Houdini 安装   | 选择 Houdini | 重新检测、详情   |

不要把所有失败都叫“不兼容”。若当前后端只给出归并状态，展示层应依据已有 attempts/error code 给出尽量准确的原因；只有信息不足时使用“无法确认可用安装”。

程序路径默认不作为编辑表单出现。点击“选择已有安装”才打开原生文件对话框；高级 override 留在 Settings。

**这轮不实现自动下载安装器或更新系统。**

---

### A4. Ready Home

Home 的唯一问题是：**“现在要打开什么？”**

顶部内容为“最近场景”，右侧两个动作：

**打开 HIP…**：主要按钮。
**空场景**：次级按钮。

下方是 Recent 列表。没有全局 Launch Studio，没有重复的目标摘要，没有成功 prerequisite 卡片，没有常驻 Logout。

#### 操作语义固定为：

| 操作                | 行为                              |
| ----------------- | ------------------------------- |
| 单击 Recent 行       | 聚焦／选中，不启动                       |
| 双击 Recent 行       | 打开该场景                           |
| Recent 行聚焦后 Enter | 打开该场景                           |
| 行内“打开”动作          | 单击打开该场景                         |
| Open HIP 选择有效文件   | 直接进入启动流程                        |
| Open HIP 取消       | 保持原页面和选择                        |
| Start Empty       | 直接进入空场景启动流程                     |
| Home 拖入一个有效 HIP   | 显示明确的“释放以打开”，释放后启动              |
| 非 Home 阶段拖入 HIP   | 保留一个待打开目标；准备完成后明确显示，不能登录成功后突然启动 |

所有“打开”必须经过同一个 activation 入口。一次双击产生的 clicked、doubleClicked、activated 信号，不能创建多个 request。

**这改变的是 UI 激活方式，不是后端“单纯选择不得创建 workspace”的不变量。** 当前已有测试需要按新动作语义调整，而不是删除 admission 保护。

---

### A5. Recent item

每个条目默认约 64 逻辑像素高，最多两行主要内容：

**第一行：文件名，较高字重；右侧为最近使用时间。**
**第二行：所在目录，较弱颜色。**

不再让文件名、目录和完整时间戳以相同字重堆成三行。

路径中间省略，但文件 basename 保持可辨认；完整路径与准确时间放 tooltip。窄窗口可以将时间并入第二行，不增加第四行。

Hover 和 selection 使用轻微表面变化。**不画整圈粉色选中边框。** 键盘焦点另行可见，不能把 hover 当焦点。

行内“打开”和 `ellipsis` 在 hover、键盘聚焦或选中时出现。右键和 Shift+F10 同样可打开上下文操作。

上下文菜单固定为：

| 条目状态 | 操作                        |
| ---- | ------------------------- |
| 正常文件 | 打开、在资源管理器中显示、复制路径、从最近列表移除 |
| 丢失文件 | 重新定位、复制原路径、从最近列表移除        |

“移除”只影响 Recent，不删除 HIP、workspace、历史或收据。现有 `SceneCatalog.remove_recent()` 已符合这一点，继续使用。

没有历史时，不显示空列表边框。仅显示一句“打开已有 HIP，或从空场景开始”，其上方仍是同一组两个动作。

---

### A6. Launching 与错误

用户激活目标后立即切换到独立 Launching 页面，不再留一页灰掉的 Home。

页面中心显示：

**正在打开 `bookcase.hip`**

下面只显示当前已知阶段：

**确认启动条件 → 启动 Houdini → 连接 Studio → 确认场景**

只呈现真实已知阶段，不伪造百分比。背景不显示完整 checklist。

**Runtime 已连接但目标未确认**，继续显示“正在确认场景”；不能提前变为成功。

**结果未知**时，同一页改为：

**尚未确认场景是否打开**
说明：**Houdini 可能已经启动。先查询原请求，避免重复打开。**

主操作只有 **查询启动状态**。此时没有新 Launch，也没有直接回 Home 再启动的捷径。

只有后端明确确认“未接纳／不存在可能存活的进程”，才能提供“返回首页，重新打开”。

确认 `target_opened` 后显示“已在 Houdini 中打开”，约 500 毫秒后**默认最小化 Launcher，不自动关闭进程**。每个 request 只最小化一次；用户主动进入详情时，不抢走窗口。Settings 提供一个“启动成功后最小化”选项。

关闭 Launcher 不代表取消或杀掉已启动的 Houdini。未知结果也不能因关闭页面被改写为失败。当前单请求和查询机制应原样保留。

---

## B. Houdini Panel

### B1. Header

Header 最多使用两行：

**第一行：当前 HIP 文件名／未保存场景；右侧为新对话图标和更多菜单。**
**第二行：当前对话名称及切换入口。**

删除重复的 `STUDIO` eyebrow、大块 header card 和“Model / Effort”表单标题。

当前 HIP 路径放 tooltip；未保存状态使用明确文字。场景替换导致旧引用失效时，出现一条可处理的上下文提示，不显示 epoch 数值。

---

### B2. 模型与 effort：紧凑、常驻、一个入口

采用一个始终可见的组合控件：

**`模型显示名 · 推理档位 ▾`**

它位于 Composer 的操作区，不进入 Advanced。点击后打开一个小型原生 popup。

Popup 固定结构：

| 区域     | 行为                                   |
| ------ | ------------------------------------ |
| 顶部     | “下一轮模型”                              |
| 模型列表   | 使用 Codex native advertised 数据，显示当前选择 |
| 搜索     | 只有可选模型超过 8 个时出现                      |
| Effort | 位于当前模型列表下方；不支持的选项不出现                 |
| 底部说明   | “选择对下一轮生效”                           |

选择立即更新**下一轮意图**；不发送请求、不创建 Thread。无需另一个 Apply 按钮。Escape 关闭 popup，已经做出的选择保留。

运行期间控件仍可见，但不可改变；显示本轮已请求设置，若收到原生 reroute 则显示实际重路由信息。下一轮选择和本轮事实继续采用当前 `ModelSettings` 的语义，不重建模型数据库。

Popup 宽度约 320–380，受屏幕可用区域限制。靠近屏幕底部时向上打开。Thread/account 变化后关闭旧 popup，迟到列表不能覆盖新选择。

---

### B3. Conversation 与 visual feedback

**助手回复不再包一整圈边框。** 采用清楚的作者标签、正文与段落间距。用户消息可以使用稍有区别的 surface，但不要每条都成为厚重卡片。

代码块、审批请求和真正的错误才使用更明确的独立容器。

工具调用默认折叠为轻量活动条，例如“读取了目标节点”“本轮执行详情”；数量和状态只能来自实际事件，不能编造完成进度。

图片直接跟随产生它的消息：

**单张图按可用宽度展示，保持比例；初始最大宽约 560，最大高约 300。** 不再套固定 244×148 小图加 208 高滚动容器。

点击图片打开同一安全产物的放大预览；多图以紧凑横向序列展示。图片加载失败显示真实原因，不用系统文件图标作为“图片预览”。

必须保留 `SafeBrowser` 不自动读取远端或任意本地资源、以及 `image_sources()` 的受控路径规则。改视觉不能绕开图片读取边界。

---

### B4. Composer 的具体结构

Composer 是一个完整组件，**只保留一个外部容器**，内部 QTextEdit 不再单独画框。

从上到下固定为：

| 层         | 内容                              |
| --------- | ------------------------------- |
| 上下文区，按需出现 | 附件缩略图与 selection chips          |
| 编辑区       | 原生多行 QTextEdit                  |
| 操作区       | Attach、Selection、模型控件、Send/Stop |
| 外部轻量提示    | 当前工作状态；必要时显示快捷键提示               |

附件使用约 56 像素缩略图，整行约 72 高，不再固定占 122。超出的附件可横向滚动或显示 `+N` 展开；移除按钮只移除本条草稿引用，不删除原文件。

Selection 呈现为 **“选择：3 个节点”**，可展开名称和路径，并可清除。过期引用明确标记，不静默替换为新场景里的同路径节点。

编辑区默认约 64 高，随内容增长到约 160，再使用内部滚动。后台状态更新不重建 editor、不切换其文档、不抢焦点。

保留 **Enter 换行、Ctrl+Enter 发送**。候选词确认不触发发送；运行中 Ctrl+Enter 不变成 Stop。

#### 宽度规则

| Panel 宽度 | 操作排列                                          |
| -------- | --------------------------------------------- |
| ≥440     | Attach、Selection 在左；模型控件靠右；最右为固定 Send/Stop 槽  |
| 340–439  | 模型控件单独占一行；下一行左侧 Attach/Selection，右侧 Send/Stop |
| 较矮 Pane  | 优先收紧附件和编辑器最大高度，保留对话、模型和 Stop                  |
| <340     | 保持可用的最低布局，不缩小正文来伪装适配；视宿主空间采用必要滚动              |

窄布局只改变呈现，不复制另一份 Composer 或另一套草稿状态。

---

### B5. Send / Stop

**Send 与 Stop 使用同一个固定位置。**

| 状态                   | 右侧动作                 | 编辑区       |
| -------------------- | -------------------- | --------- |
| Idle，可发送             | 粉色 Send，`arrow-up`   | 可编辑       |
| Idle，不可发送            | 禁用 Send，必要时说明原因      | 可编辑       |
| Submitting / Working | Stop，`square`        | 可继续写下一段草稿 |
| Stop 请求中             | 禁用重复点击，显示“停止请求已发送”   | 可编辑       |
| 已停止且结果确定             | 恢复 Send              | 保留后续草稿    |
| 提交／执行结果未知            | 不允许重新发送原操作；提供“查询原状态” | 草稿保留      |

Stop 使用高对比中性按钮，不是巨大危险红按钮；它通过固定位置、图标和旁边的工作状态保持明显。

**一个停止请求不能把未知副作用显示成已撤销，也不能把 Codex interrupted 当作 HOM 已停止。**

---

### B6. Consent、审批和错误

正常情况下，授权状态只占一条轻量入口：

**“逐次确认”／“本对话已授权”**

点击才展开范围、撤销和本机执行风险说明。继续使用现有 scoped consent，不改审批策略来迁就视觉。

真正出现审批时，卡片先显示：

**要做什么、作用于哪里、需要你允许什么。**

例如先呈现“允许写入这个目录”和规范化目录路径；原始 JSON 放进“完整请求”。不隐藏权限范围，不把高风险确认压缩成只有一个含糊 Allow。

审批区域最多使用可用 Panel 高度约 30%；内容长时卡片内部滚动，Stop 和 Composer 不得被挤出视野。

错误分为三层：

**局部问题**留在对象附近；**本轮失败或部分完成**留在该轮消息附近；**连接、未知副作用或存储问题**使用持续的工作状态提示。不要同时在顶部、底部和卡片中重复三遍同一错误。

Diagnostics 可以看到完整原始信息，但默认对话不出现 executable path、Bridge、Runtime ID、receipt JSON 或 stderr。

---

# 第四部分｜Modern Visual + Icon Specification

## 1. 参考对象与采用的原则

本轮参考的是交互模式，不复制外部产品品牌。

| 参考                        | 采用的模式                    | 不采用的东西     |
| ------------------------- | ------------------------ | ---------- |
| Cursor onboarding         | 登录与开始工作分阶段，不把所有前置任务铺在工作区 | 品牌、页面样式    |
| Raycast Action Panel      | 聚焦对象有明确主动作，次要动作进入上下文菜单   | 完整命令平台     |
| Linear 列表交互               | hover、键盘焦点和对象操作分开处理      | Issue 管理模型 |
| ChatGPT Windows companion | 紧凑界面仍保留模型和附件入口           | 网页实现、会话架构  |

这些模式分别有官方流程和交互文档支持。([Cursor][1])

## 2. 色彩和边界

**保留当前中性深色与柔和粉色方向，但改变颜色的使用规则。**

| Token / 角色       | 决定                           |
| ---------------- | ---------------------------- |
| 页面底色             | 保留 `#17181C`                 |
| 普通 surface       | 保留 `#202127`                 |
| Popup / Composer | 保留 `#292B33`                 |
| 主要文字             | 保留 `#F4F4F6`                 |
| 次要文字             | 保留 `#C3C5CE`                 |
| 元信息              | 保留 `#989CAA`                 |
| 品牌／主要操作          | 保留 `#EFA2BD`，使用深色前景          |
| 选中背景             | 保留弱粉中性色 `#392A34`，不用整圈粉框     |
| 装饰性分隔            | 降至约 `#333640`，并减少使用          |
| 真正输入控件边界         | 可保留 `#6E7382`，从默认 2px 改为 1px |
| 焦点               | `#F7BCD2`，仅在需要表达焦点时明显出现      |
| 成功／警告／错误         | 继续独立语义色，不用粉色代替               |

**无边框优先的区域：** Header、普通助手消息、Recent 列表容器、图片外层、Composer 内部编辑器。

**需要明确边界的区域：** Popup、独立输入、审批和错误详情。

普通按钮主要靠 surface 与 hover 区分。只有焦点需要更强轮廓，不允许为了留出焦点边框而默认给所有控件画 2px 框。

---

## 3. 字体、密度与响应式

保留系统字体及中文 fallback，不新增必须安装的字体。

| 项目             | 规格                          |
| -------------- | --------------------------- |
| 正文             | 10.5–11 pt                  |
| 次要信息           | 9.5–10 pt，不承担关键错误           |
| 区域标题           | 12–14 pt                    |
| Auth/Setup 主标题 | 18–20 pt                    |
| Panel 外边距      | 普通 12，窄 Pane 8              |
| Launcher 内容边距  | 24–32                       |
| 间距梯度           | 4、8、12、16、24、32             |
| 控件圆角           | 6                           |
| Popup / 普通独立容器 | 8                           |
| Composer       | 10–12                       |
| 图标动作点击区域       | 至少约 32×32，Send/Stop 为 36×36 |
| Launcher 主动作高度 | 40–42                       |

Qt 已使用逻辑坐标，不能再手工按 Windows 百分比把整个布局乘一次。图标缓存和图片需分别处理 DPR；不能为 Studio 改 Houdini 的全局字体、样式或 DPI 策略。([Qt文档][2])

---

## 4. 动画与状态

动画仅承担反馈：

**Hover 约 100 毫秒；页面内容淡入/淡出约 150 毫秒；Popup 直接或短过渡出现。**

不做页面飞入、背景粒子、视差和循环装饰。页面切换不改变窗口尺寸。

Loading 统一使用批准的 `loader-circle`，只在可见的忙碌控件中旋转；隐藏、最小化或 Idle 时停止动画。状态文字是主要信息，旋转不是完成保证。

错误必须包含文字，不只依赖颜色。禁用按钮不能成为唯一解释；关键原因应在相关区域可读。

---

## 5. 图标体系：本轮正式冻结

### 来源与版本

**唯一产品图标来源：Lucide Outline SVG。**

固定资源版本：

```text
Repository: lucide-icons/lucide
Tag: 0.468.0
Commit: f12b0de177fbc2a6795e99be065887e72b237123
Source directory: icons/
```

这是一组固定设计资源，不是需要不断升级的运行时依赖。该 tag 与提交对应关系已核对。

许可证采用上游 ISC，并保留 Feather 派生部分所需的 MIT 版权与许可说明。允许随产品分发，但必须包含相关通知；不能只写一句“图标来自 Lucide”代替许可证。([Lucide][3])

### 批准清单与用途

| SVG 名称            | 唯一批准用途               |
| ----------------- | -------------------- |
| `folder-open`     | Open HIP             |
| `file-plus-2`     | Start Empty          |
| `ellipsis`        | 更多／条目上下文入口           |
| `square-pen`      | 新对话                  |
| `paperclip`       | 添加图片附件               |
| `mouse-pointer-2` | 引用 Houdini Selection |
| `arrow-up`        | Send                 |
| `square`          | Stop                 |
| `x`               | 移除草稿附件／引用，关闭产品 Popup |
| `chevron-down`    | 模型、会话等展开入口           |
| `chevron-right`   | 折叠详情                 |
| `arrow-left`      | 次级页返回                |
| `arrow-down`      | 回到对话最新内容             |
| `search`          | 模型列表搜索，仅达到显示条件时使用    |
| `settings`        | 设置入口                 |
| `external-link`   | 打开浏览器／外部说明           |
| `check`           | 选中模型、短暂成功标记          |
| `triangle-alert`  | 警告、部分完成、需要注意         |
| `circle-alert`    | 明确错误                 |
| `loader-circle`   | 忙碌反馈                 |
| `refresh-cw`      | 查询／重新检查，不代表重放场景操作    |
| `maximize-2`      | 图片放大                 |
| `copy`            | 复制诊断或明确文本            |

**未列出的用途使用纯文字。Codex不得自行再挑“差不多合适”的图标。**

`Relocate`、`Remove from Recent`、账号邮箱、版本号、普通路径，不需要额外图标。正常 Home 不恢复三行绿色成功图标。

### 品牌规则

**Launcher 和 Panel 不使用图形 Logo。只使用产品文字或当前场景上下文。**

ChatGPT 登录按钮使用文字，不临时绘制或拼装 OpenAI Logo。

当前 `StudioGlyph` 和产品界面中使用的 `QStyle.SP_*` 应替换或删除。操作系统原生标题栏、原生文件对话框自身的系统图标不属于需要篡改的产品图标。

### Qt 实现规则

上游图形保持：

**24×24 viewBox、2 单位 stroke、round cap/join、原始 path 不变。** 这些属性可从固定版本的原始 SVG 直接核对。

图形默认绘制为 20 逻辑像素，元信息用 16，单独状态图可用 24。只改变颜色、尺寸和明确的 loading 旋转；不修改图形结构。

只打包清单中的 SVG。使用一个统一 loader，经 `QSvgRenderer` 渲染并按名称、色彩、尺寸、DPR 缓存。`QSvgRenderer` 支持加载 SVG 并绘制到 Qt paint device，不需要引入 Web frontend。([Qt文档][4])

**允许 QPainter 渲染已批准 SVG、绘制文字和控件背景；禁止使用 QPainter 发明图标路径。**

资源缺失时退回文字并报告诊断，不能退回随机系统图标或 emoji。

---

# 第五部分｜给 Codex 的详细执行 Brief

## 任务

**在 PR #5 的现有产品逻辑上完成 staged Launcher 与 integrated Panel presentation，停止继续扩展后端范围。**

第二至第四部分是本轮已确定的产品规格。实现过程中不得自行更换页面模型、按钮布局或图标体系。

### Baseline

```text
Repository:
Big-chicken-hen/Big-Chicken-Houdini-Studio

main:
557a393e70c5f6f96d2a8e60e7428b243b29e39e

PR:
#5

Branch:
codex/ui-productization

Review head:
99761e99c94588e4876297992836a78ae8c1596d

Icon source:
lucide-icons/lucide
f12b0de177fbc2a6795e99be065887e72b237123
```

开始前确认远端及本地变更。不得回退后续工作来匹配这个 SHA。

---

## Stage 0 — 冻结业务范围，建立页面投影

先实现一个小型 Launcher 页面选择函数和有限页面容器，再调整样式。

输入继续使用现有：

**Onboarding snapshot、account 状态、target、launch record 和 request identity。**

输出是：

**Checking / Setup / Authentication / Home / Launching，以及局部 error/waiting/opened 状态。**

使用现有 QWidget / QStackedWidget 即可。不引入路由库、全局 store、事件溯源或状态持久化系统。

需要保留的实现包括：

| 模块                            | 禁止借 UI 重写的部分                                             |
| ----------------------------- | -------------------------------------------------------- |
| `onboarding.py`、`accounts.py` | 官方认证、同一程序与 Codex home、客户端关闭与 generation                  |
| `targets.py`                  | HIP 规范化、Recent 关联、remove 不删除文件、admission 时创建内部 workspace |
| `launcher.py`                 | 单启动请求身份、所有权、未知结果查询                                       |
| `output.py`、路径实现              | 输出优先级、用户数据与 cache 边界                                     |
| `codex/settings.py`           | 原生模型、catalog 和 turn 设置                                   |
| Runtime / ledger / artifacts  | scene identity、执行语义、持久收据、图片引用                            |
| consent                       | 当前严格关联、撤销、未知回复不重发                                        |

页面 enter/leave 不得触发新的 probe、认证或启动副作用。只有明确 action 和现有生命周期需要才调用服务。

---

## Stage 1 — 先完成 Launcher flow，不先堆样式

施工顺序：

**页面投影 → Setup/Auth → Home 直接打开 → Launching/Unknown → Settings/Diagnostics。**

具体要求：

**删除 `primary_action()` 的跨业务万能分发。** 不同页面按钮直接连接不同语义动作，但所有场景激活统一进入一个入口。

Home 的 Open HIP、Empty、Recent double-click/Enter 和 drop 使用同一个启动接纳逻辑。保留 activation guard，一次意图只获得一个 request ID。

任何 `process_may_exist` 或启动结果未知状态，都不能通过返回 Home、页面重建或重新登录绕过查询保护。

Recent 的 Relocate、Remove、Reveal 和 Copy 放入对象菜单；更改 QWidget 排列不改变 `SceneCatalog` 的数据语义。

认证成功自动转入 Home；账号未知不伪装为退出。浏览器重开不创建新 loginId，取消等待权威结论。

成功最小化只绑定确认过的 request，不绑定页面 render 次数。用户重新展示 Launcher 时，不能再次立即最小化。

**这一步完成后，即使还没应用最终图标，产品流程也应已经符合规格。**

---

## Stage 2 — 固定图标资源与有限视觉组件

导入批准的 Lucide SVG 子集与许可证，建立有限 `icon(name, size, color, dpr)` 入口。可以使用一个白名单映射，但不能发展成图标插件系统。

明确禁止：

**Codex不得自行设计、绘制、发明或选择产品图标。不得画鸡、Logo、AI sparkle、电脑、私有状态符号；不得用 emoji 或 `QStyle.SP_*` 补空位。没有批准图标就使用文字。**

修改 `theme.py` 的角色规则，而不是再建第三套 Launcher QSS：

**surface、text hierarchy、button role、focus、Composer、Popup、Recent row、error。**

移除全局的“所有按钮／所有输入均为 2px 边框”规则。编辑器保留原生行为，不为边框动画反复替换它。

可以为 Recent 使用小型 delegate 绘制文字、背景和批准 SVG；不需要搭通用虚拟列表系统。

Popup 也必须使用自己的受控 Studio 根样式，不能为了让 Popup 变色而修改 Houdini QApplication 的全局 palette/style。

---

## Stage 3 — Panel 重排：先 Header 和模型，再 Composer 与图片

### 3.1 Header 与 Model

压缩 Header，将当前模型呈现替换为常驻组合控件。

保留 `ModelSettings` 中已有的 native revision、account/catalog revision、下一轮 override 和 reroute 语义。可以把状态与视图分离成两个小对象，但不得重新实现模型同步协议。

模型 Popup 必须在窄 Pane 与屏幕边缘可用；切换 Thread/account 后旧 Popup 和迟到结果不能修改当前意图。

### 3.2 Composer

保留同一个原生 QTextEdit 和现有每对话 QTextDocument。重新安排其容器、附件、selection、模型和动作槽，不在状态轮询中重建它们。

将附件区压缩到规格尺寸，区分“草稿附件缩略图”和“对话结果大图”，不能用同一个固定宽高适配所有用途。

Send/Stop 固定位置切换；后台 working 不禁止本地打字。Ctrl+Enter 只能发送，不承担取消。

### 3.3 Conversation 与图片

去掉普通助手消息的外框，减少工具事件占用。图片按 available width 呈现，支持点击放大；不改变受控图片来源。

必须保留 widget 复用、滚动位置和异步图片加载的生命周期保护。用户在阅读旧消息时，新消息不能强制滚到底。

### 3.4 Consent 与错误

减少默认状态行数量；保留必要的不确定性和执行事实。

权限卡先解释操作、目标与范围，再允许展开原生对象。不能把有意义的权限字段隐藏到用户无法判断的程度，也不能把普通原生表单自动当成工具许可。

**同一错误只指定一个主要呈现位置。** Diagnostics 保留原始对象，不将结构化错误退化成纯字符串。

---

## Stage 4 — 旧 HIA 的使用边界

本次重新读取的旧 Composer 确实提供了原生 QTextEdit、局部快捷键、图片粘贴分流和基于文档尺寸调整高度的实现。

继续参考：

```text
houdini_package/python_libs/hia_panel/composer.py

ExpandableTextEdit
ExpandableTextEdit.insertFromMimeData
ExpandableTextEdit._update_height
AttachmentStrip
```

但当前 Studio 已经增加了更明确的 per-thread document、迟到回调和提交快照保护。**不要为复用旧代码退回旧路径列表、旧 Panel 状态或每次重建附件条的方式。**

本轮不涉及新的 viewport、材质、Solaris 或模拟能力，没有理由重新读取并迁移整个旧 executor。

---

## Stage 5 — 更新测试：保护行为，不保护旧 Dashboard

现有 Launcher 测试明确检查了 target selection 不 admission、未知启动查询同一 ID，以及账号 unknown 不等于 signed out。后两项继续保持；第一项保留在纯选择层，但 Open HIP/Empty 的 UI 激活测试必须按新规格更新。

### 测试矩阵

| 类别             | 必须覆盖                                                     |
| -------------- | -------------------------------------------------------- |
| 页面投影           | Codex/Houdini/账号不同状态；启动中优先；Unknown 不回到可重复启动的 Home        |
| Authentication | 用户点击才打开浏览器；完成自动进 Home；取消、重开、账号查询失败、迟到通知                  |
| Returning user | 不出现签出页闪烁，不要求重复确认成功 checklist                             |
| Home           | Open/Empty 直接启动；Recent 单击不启动、双击/Enter 只启动一次              |
| Recent         | 缺失文件、Relocate、Remove 不删除文件、context menu 键盘可达             |
| Launch         | 一个 request；丢响应查同 ID；connected 不冒充 target_opened；成功只最小化一次 |
| Model          | 原生恢复、catalog 更新、无效模型、effort 变化、reroute、运行中锁定             |
| Composer       | 真正的草稿保留、文本/图片粘贴、Thread 切换、发送期间继续输入                       |
| Stop           | 固定位置、无重复请求、原生对话与 HOM 结果分别确认                              |
| 生命周期           | 页面切换和关闭后，迟到回调不更新已销毁控件                                    |
| Icons          | 只使用白名单，资源可打包，许可证在交付物中，加载失败不回退系统图标                        |

不要为了新页面复制两套后端 fixture。改现有测试和少量状态 fixture 即可。

### 预览要求

必须输出以下独立状态，而不是只输出一张漂亮 Home：

**Checking、Codex 缺失、Houdini 缺失、Signed out、等待浏览器、账号未知、Ready 有/无 Recent、丢失 Recent、Launching、Launch Unknown、Opened。**

Panel 输出：

**Idle、Working、Approval、Unknown、模型 Popup、带附件、单张结果大图、无效模型、窄 Pane。**

Launcher 检查 100%、125%、150%、200%。Panel 检查 360、440、720 宽度；其中窄 Pane 的关键状态至少再做 150%/200%。

不把所有组合做成无限矩阵。重点是：**无横向裁切、Stop 和模型入口始终可达、对话没有被表单挤没、Popup 不出屏幕。**

---

## Stage 6 — 真实验收

使用当前候选提交，在专用测试用户状态和场景中完成，不清除真实用户账号或项目数据。

### 首次使用

**Signed out → 启动 Launcher → 只出现认证体验 → 点击官方登录 → 浏览器完成 → 自动进入安静 Home → Open HIP／Empty → 独立 Launching → 确认目标后最小化 → 打开真实 Panel。**

在 Panel 中选择模型与 effort，使用 Microsoft Pinyin 输入任务，粘贴文本和图片，引用真实 selection，发送一个小型 Houdini 修改任务，观察 working 和结果反馈，再继续一轮。

真实认证不是只运行 `account/read`。现有 signed-out probe 是有用的准备证据，但不能代替浏览器登录完成。

### Returning user

**重新打开 Launcher → 必要检查正常 → 直接 Home → 双击最近 HIP → 一次启动。**

不要求再次点“环境 Ready”，不重新输入路径，不新建 workspace。

### 异常路径

确认账号网络错误不伪装退出；丢失启动响应不产生第二个 Houdini；未知提交不自动重发；关闭 Launcher 不杀已启动 Houdini。

running-HOM Stop 只验证真实可达性、请求时间和最终状态，不新增“任意 HOM 即时强制中断”的目标，也不能为了通过验收改变主线程安全。

---

## Git 与 PR 决定

**本轮继续在 PR #5 完成有边界的 presentation correction，不再先合入一个尚未完成用户验收的页面骨架，再把验收转给下一个 PR。**

理由是：当前仍是 Draft，本轮改的是同一“UI productization”范围，而且主要后端已经完成。再把尚未完成的认证和用户流程向后转移，会让阶段边界越来越难判断。

但从现在开始冻结新增业务范围：

**只改页面投影、Launcher flow、Panel 布局、已批准资源和必要回归；不再扩 storage、协议、权限或 Houdini capability。**

建议按实际变化形成约五个语义提交：

```text
refactor(launcher): introduce staged onboarding and stable page actions
refactor(launcher): make Home a direct scene-opening surface
style(ui): apply the approved visual and Lucide asset specification
refactor(panel): integrate model context composer and visual feedback
test(ui): verify staged onboarding and native authoring interaction
```

测试与对应行为修改可以同提交；最后一个提交记录跨组件验收，不要求为了凑数量拆分。保留已经公开的提交，不 force-rewrite `main` 或现有历史。

### Merge Gate

PR #5 可合入的条件是：

**页面流符合本规格；只有真正需要的 prerequisite 才出现；Home 直接打开目标；启动不重复；模型与草稿语义不退步；图标只有批准资源；真实官方登录和 Houdini Panel 的最小用户流程完成；未通过的场景如实列出，不能再次用离屏截图替代。**

视觉验收不等于“Codex觉得更现代了”，而是逐项核对：**页面是否只要求一个当前任务，控件是否具有稳定语义，窄 Pane 是否把主要空间还给对话，内部状态是否在正确层级出现。**

---

**最终方向不是“把现在这张 Dashboard 再做漂亮一点”，而是让 Studio 在不同阶段自然成为不同的体验：缺环境时帮助完成 Setup，未登录时帮助完成认证，Ready 时只帮助打开场景，进入 Houdini 后只帮助用户表达、观察和继续创作。**

**这次不再把产品结构、图标和布局决定留给施工过程。上述页面、动作、视觉与资源规范，就是 Codex 下一轮的施工边界。**

[1]: https://cursor.com/docs/get-started/quickstart "Quickstart | Cursor Docs"
[2]: https://doc.qt.io/qt-6.8/highdpi.html "High DPI | Qt 6.8"
[3]: https://lucide.dev/license "License – Lucide"
[4]: https://doc.qt.io/qt-6.8/qsvgrenderer.html "QSvgRenderer Class | Qt SVG 6.8.8"
