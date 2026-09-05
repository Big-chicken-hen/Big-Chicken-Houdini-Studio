# 第一部分｜独立审查结论

## 1. 结论：方向基本正确，可以停止大规模架构重写

**Studio 当前没有偏离核心产品目标。执行架构已经基本成立，下一阶段应该转向真实 Houdini 工作验证，而不是再换一套架构。**

但这个判断不等于“已经可以作为成熟工具使用”。更准确的定位是：

> **核心执行边界设计合理，已经有针对性故障测试；仍需修复少量确定问题，并通过真实 Houdini GUI、真实 Codex 推理和实际创作任务证明可用性。**

这次审查以 `main@16c29e542f0298c72d5026a841c0778ea676a865` 为基线。最后重新查询时，`main` 仍然停留在该提交。

另需明确交接状态：你的补充到达之前，我已经创建了 `studio/product-readiness` 上的四个提交和草稿 PR #1；**它们尚未合入 `main`，不计入下面对当前主线的评价，也不应被 Codex 自动视为已批准方案。**补充之后没有再修改仓库。

---

## 2. 为什么我认为这次架构成立

### 实际链路已经围绕“完成场景工作”组织起来

当前实现中，Launcher 启动 supervisor，**Bridge 实际运行在 supervisor 进程中**，并不是额外再启动一个同职责服务。Bridge 启动 Codex App Server，再启动 Houdini；Codex 使用独立的 MCP stdio 子进程，访问 Houdini 内的 Runtime。

实际职责分配如下：

| 环节                        | 真实职责                             | 判断                |
| ------------------------- | -------------------------------- | ----------------- |
| Launcher / supervisor     | 环境选择、启动、进程归属、workspace 排他使用      | 合理，没有承担 Agent 规划  |
| Panel → Bridge            | 用户输入、原生会话、审批、附件、状态投影             | 合理，不直接负责判断 HOM 成败 |
| Bridge → Codex App Server | 使用原生 Thread/Turn、历史与事件           | 应保留               |
| Codex → MCP               | 七个面向任务决策的工具                      | 数量和颗粒度基本合理        |
| MCP → Runtime             | 提交操作、等待或查询原 operation receipt    | 正确                |
| Runtime → 主线程             | 同一有界队列，执行入口校验 scene epoch        | 正确且必要             |
| HOM → receipt             | 分开记录脚本执行、检查结果和不确定性               | 正确                |
| receipt → Panel           | 展示 Runtime 的执行事实，不拿 Codex 完成事件代替 | 正确                |

其中最重要的三件事，已经落实在代码，而不只是文档里：

**第一，场景身份校验和 HOM 位于同一个主线程回调。**

`OperationRuntime._on_main_thread()` 在真正执行前检查 `scene_epoch`，不是仅在 HTTP 接收时检查。Houdini 的 load/clear 回调会推进 epoch；同一路径重新加载也不会继续沿用原观察身份。

**第二，操作事实不会因为 HTTP 响应丢失而消失。**

接纳时先保存 queued receipt；运行前保存 running；完成后保存结果与终态。同一个 operation ID 绑定 payload hash，查询原 ID 不会执行脚本，不同内容重复使用该 ID 会被拒绝。这里并没有虚构任意 HOM 的跨进程 exactly-once 保证：崩溃恢复时，原 running 操作仍明确记为 unknown。

**第三，脚本执行成功和任务检查成功已经分开。**

`execute()` 会先确认脚本执行结果，再分别处理 checks、观察和结果转换。后置检查失败不会把已经发生的场景修改重新描述成“没有执行”。通用 HOM 的 `automatic_retry_safe` 也没有因 Undo 分组而变成 true。

这三点解决的是实际的副作用与并发问题。**它们不是应该被“极简化”掉的基础设施。**

---

## 3. 新版目前没有重新长成一个过度设计的平台

我没有看到必须再砍掉一个大型核心 subsystem 的证据。

当前的复杂机制，大部分都有清晰用途：

| 机制                   | 是否值得保留 | 原因                                 |
| -------------------- | ------ | ---------------------------------- |
| scene epoch          | 保留     | 阻止旧场景观察作用到新场景                      |
| operation ledger     | 保留     | 解决结果丢失、重复提交、崩溃后不确定性                |
| 单一场景队列               | 保留     | 统一读、cook、capture、写的执行顺序            |
| 不执行 HOM 的 health     | 保留     | 将“服务存活”与“主线程是否忙”分开                 |
| workspace 身份与锁       | 保留     | 隔离数据，避免同一 workspace 被两个 GUI 会话同时占用 |
| 原生 Codex Thread/Turn | 保留     | 不再维护第二套持久聊天系统                      |
| 显式 memory、可选 FTS     | 保留     | 小而独立，没有绑住核心启动                      |

Runtime 的 health 只读取缓存；本地文档检索与显式记忆位于 workspace 数据层，不依赖实时 Houdini 执行。Launcher 也没有导入知识库、构建向量或组织自动恢复提示的流程。

**三个小 SQLite 文件，也不等于出现了数据库平台。** operation、memory、documents 的生命周期和失败影响不同，分开存放有合理性。我不建议为了“统一”把它们合成一个更大的存储抽象。

真正需要警惕的是以后新增的东西：

> 不要把每一次任务失败都升级成一个新 recovery subsystem；不要把每一种 Houdini 能力都升级成一组新 MCP tools；不要把每一种 UI 请求都升级成一套状态管理框架。

目前应该守住已有边界，而不是继续发明边界。

---

## 4. 已确认的局部问题

### A. 当前 `main` 的 CI 分层确实有错误

主线 workflow 声明 backend-only 安装，不安装 Qt，但随后 `scripts/check.py` 默认发现全部 `test_*.py`，其中包括直接导入 PySide6 的 `test_ui.py`。我读取的主线运行日志中，四个矩阵任务都因此失败。

这不是“测试太少”，而是**依赖边界和测试发现范围不一致**。

修法很小：后端明确不加载 Qt 测试，另设一个真正安装 Qt 的 UI job。不要简单把 PySide6 缺失全部改成 skip，否则会把 UI 检查悄悄变成无人执行。

### B. 冻结的异常类会掩盖原始错误

`BridgeError` 使用 `@dataclass(frozen=True)`。我读取的 Python 3.13 CI 日志中，`contextlib` 更新异常的 `__traceback__` 时触发 `FrozenInstanceError`，原本的 Codex timeout 被另一层异常覆盖。

**这是异常对象定义错误，不需要重写 Codex 集成。**

去掉异常类的冻结限制，保留现有结构化错误字段，再加一个跨 context manager 的异常传播回归测试即可。这里应修异常类，不应删掉有价值的 Python 3.13 检查。

### C. 不存在的节点，可能通过“输入为空”检查

`HoudiniScene.checks()` 的 `input_equals` 分支，在节点不存在时使用空输入列表。如果期望值是 `None`，最终比较就会通过。

我对原始方法做了隔离复现，得到：

```text
节点：/obj/does_not_exist
检查：input_equals，expected=None
结果：passed=True
```

这不是实时 Houdini 测试，但足以证明该分支的逻辑错误。

**“节点不存在”和“节点存在但输入未连接”不能作为同一事实。**

该问题也可能影响 precondition：原本应该阻止执行的缺失目标，可能被当作前置条件成立。修复范围应限于检查逻辑及对应测试，不要因此增加一整套场景验证框架。

### D. Panel 的历史回填存在实时事件遗漏窗口

`Panel.apply_events()` 会推进 cursor，但在 `self.hydrating` 为 true 时不把事件交给 transcript。`refresh()` 虽然会避免在回填期间发起新的 events 请求，**已经在途的 events 响应仍然可能落入这个窗口**。

我对原始 callback 做了隔离复现：收到一条 delta，cursor 从 1 推进到 2，但事件没有应用，也没有安排后续回填。

可能的实际表现是：消息暂时缺字、工具事件没有出现，直到之后的完整历史读取才恢复。是否长期缺失取决于后续事件和回填时序，不能夸大为“聊天数据已经丢失”。

需要修的是**历史快照与实时事件的衔接**，不是重新建立聊天数据库。修复必须同时测试“不漏事件”和“不重复拼接 delta”。

### E. 错误信息和工具 schema 还不够利于 Codex 自行修正

这里有两类成本。

一类是 MCP 的 `checks`、`preconditions`、`views` 当前主要使用宽泛的 object 数组，很多约束只存在于 Runtime 验证逻辑里。例如 checks 实际需要 `kind`，但工具描述没有完整呈现对象形状。模型可能需要靠失败后重试才学到正确格式。

另一类是错误被压缩得过头：脚本编译失败被转换成泛化的 “The HOM script did not compile”，没有向 Agent 提供足够直接的行号和语法错误信息。

建议是：

**稍微增加输入契约的明确性，换取更少的错误 tool calls；稍微增加安全的错误定位信息，换取更少的盲目修复。**

不要把“降低 context”机械理解成“schema 越短越好、错误越模糊越安全”。

---

## 5. Panel 状态复杂度：已有局部问题，但没有理由整体推倒

当前 Panel 确实有不少 flags，但不能把它们全部归为坏设计。

这里至少存在三种不同的状态：

| 状态类别                                 | 权威来源            | Panel 应如何处理  |
| ------------------------------------ | --------------- | ------------ |
| Codex 当前 Thread/Turn                 | Codex 原生事件与读取结果 | 投影，不能自行宣布完成  |
| 场景操作 queued/running/finished/unknown | Runtime receipt | 投影，不能从聊天事件推断 |
| 正在上传、切换会话、回填历史、提交输入                  | Panel 请求生命周期    | 本地临时状态       |

目前代码已经在区分这些来源，尤其没有把 Codex interrupted 当成 HOM cancelled。这个方向正确。

需要改善的，是相互排斥的请求状态和异步回调有效性，而不是把所有状态统合进一个全局 store。

我的建议是：

**先修具体竞态；当同一组互斥 flags 确实反复出问题时，再收成一个小状态对象。**

例如提交输入这一组，可以明确表达“未提交、提交中、提交结果未知”，而不必让多个 boolean 任意组合。但附件上传、记忆操作、历史回填可能同时发生，不该被强行塞进一个全局枚举。

另外，Qt API 当前主要向失败 callback 传递错误字符串，`send_failed()` 又统一设置 `uncertain_send=True`。这使得“明确在提交前拒绝”和“网络丢失、是否提交未知”容易被同样处理。应保留足够的结构化错误信息，让确定的拒绝恢复编辑，只有真正的不确定提交才要求 reconciliation。

---

## 6. Agent 效率：简单任务可以很短，但还需要真实验证

以“创建一个 Box，size 设为 2”为例，当前架构允许：

**首次操作：一次 `hia_context`，一次 `hia_execute_hom`，并在同一批次内回读或检查。**

已有有效观察、目标明确时，可以直接执行下一批次。没有必须查询知识库、先列 capability、全场景 inspect、独立 validate、再截图的协议要求。现有工具设计和场景指令支持这条短路径。

但要区分：

> **架构允许两次调用完成，不等于真实 Codex 已经稳定只用两次调用完成。**

下一阶段应该测真实任务，而不是继续凭 schema 推测 Agent 效率。

程序侧，Adapter 当前内部每 80 毫秒查询一次 receipt，最多等待约 8 秒再返回未完成状态。**这是程序内部轮询，不是每 80 毫秒让模型再 reasoning 一次。**没有实测瓶颈前，不建议为它新增推送服务或另一套事件协议。

Agent 侧，优先优化顺序应该是：

**输入形状明确 → 错误可修正 → 简单批次内完成必要回读 → 减少重复观察 → 再考虑更细的传输优化。**

七个工具已经足够小，不需要为了证明“更精简”继续减到三个。

---

## 7. 真正尚未证明的，是 Houdini 里的使用体验

### 主线程执行正确，不代表长任务期间 Panel 一定可交互

这是必须提高优先级的真实验收点。

Runtime 使用主线程执行 HOM，同时允许其他线程请求取消，这是正确的。但 Panel 自己也在 Houdini GUI 线程里：

> 长时间占用主线程的 HOM，可能让用户根本来不及点击 Panel 的 Stop。

后台线程成功设置取消标志，和用户在真实 Panel 上能够发出停止请求，是两项不同能力。当前 fake 测试不能证明后者。

这里不能提前许诺“任何长 HOM 都能即时停止”。也不要为了按钮看起来流畅，随意加入 `processEvents()` 引发重入，或者把 `hou` 操作搬到任意后台线程。

先在真实 Houdini 中测清：哪些操作会让出交互、哪些原生 cook 可中断、哪些只能等当前小批次结束。

### Screenshot 也需要真实副作用测试

当前 capture 复制现有 flipbook settings，再修改帧、输出和分辨率，并恢复原帧。这个起点合理。

但 flipbook settings 还包括模拟初始化、motion blur 等可能显著改变成本与行为的选项。不能只证明“产出 PNG”，还要验证捕获不会意外继承用户上次 flipbook 的高成本设置或重置模拟。SideFX 的接口明确包含这些选项。([SideFX][1])

### 通用 HOM 不等于已经具备完整的产品能力

目前通用执行入口可以表达材质、灯光、动画和 Solaris 工作，但这不等于相关工作已经验证。

当前主线的 smoke 是离线导入与环境检查；现有故障测试主要依靠 fake HOM。**还不能据此宣布真实建模、Karma、图片理解或者完整 Codex→Houdini 链路已经通过验收。**

因此，现在最大的缺口不是“少了哪个框架”，而是：

**缺少一组小而真实、可以反复运行的 Houdini 任务证据。**

---

## 8. 保留、简化、重构、删除的最终判断

| 处置           | 建议                                                                                   |
| ------------ | ------------------------------------------------------------------------------------ |
| **保留**       | 当前进程职责、App Server、七工具方向、scene epoch、ledger、统一队列、cached health、workspace 隔离、显式 memory |
| **简化**       | 不必要的重复错误包装；过度泛化的 UI 提交处理；永久规则中的一次性协作说明                                               |
| **局部修复**     | CI 分层、异常传播、缺失节点检查、历史回填竞态、工具输入形状、可操作的脚本错误                                             |
| **暂不整体重构**   | Panel、Runtime、Bridge、ledger、workspace 数据层                                            |
| **没有充分理由删除** | operation receipt、队列、SQLite、文档 FTS、原生历史投影                                            |
| **不要新增**     | embedding 核心依赖、自动恢复规划器、第二套聊天历史、通用任务调度平台、逐节点工具森林                                      |

Git 主线也不需要重建 baseline。我只读检查到的主线是 **9 个线性提交，没有 merge commit**，主要提交含义已经能看懂。个别 integration 提交边界不够细，不足以成为重写公开历史的理由。

**最终判断：架构基本成立；修边界、跑真机、交付真实能力。**

---

# 第二部分｜可直接交给 Codex 的执行 Brief

## 任务定位

继续开发 `Big-chicken-hen/Big-Chicken-Houdini-Studio`。

**本轮不是第二次架构重写。** 默认保留当前系统边界，优先完成真实 Houdini 纵向链路，修复已确认的局部缺陷，然后重新设计 Launcher。

审查基线为：

```text
main: 16c29e542f0298c72d5026a841c0778ea676a865
```

施工前重新确认当前 `main`、工作区变更和远端分支，不能假设仓库仍停在该提交。

### 已有草稿的处理

仓库已有一个未合入的草稿 PR #1：

```text
branch: studio/product-readiness
head:   36081143f9fbe6f365fc01dcda57fff981cc3507
```

包含四个提交：

| 提交        | 内容                      |
| --------- | ----------------------- |
| `a06f3e7` | backend / Qt CI 分层      |
| `08f3b28` | Codex 异常 traceback 兼容修复 |
| `b49abc8` | Launcher 科幻视觉草稿         |
| `3608114` | opt-in Houdini smoke 草稿 |

**先审阅，再决定复用、调整或不采用。不要自动合入，也不要自动删除。**

其中 Launcher 草稿只代表一个青紫科幻方向，不代表已经完成用户要求的二次元视觉验收；smoke 草稿没有运行过真实 Houdini，不能当成通过证据。

草稿 CI 中为本次远程审阅增加的完整 `source.bundle` 打包，没有必要成为长期产品流程。常规 UI evidence 保留截图、环境版本和 commit SHA 即可，不要每次携带完整 Git 历史。

---

## A. 本轮必须守住的边界

### 不要改变的核心设计

继续由 Runtime 唯一负责 scene identity、场景队列和 operation receipt。

继续使用 Codex 原生 Thread/Turn、历史、审批和自动 compaction。App Server 原本就提供持久 Thread 和可恢复的原生历史，不应再发展平行聊天存储。([OpenAI][2])

保持文档检索和显式记忆独立于 live Houdini。

保持通用 HOM，不引入固定节点白名单，也不假装把任意 Python 变成安全沙箱。

保持查询原 operation ID 恢复结果，不为恢复响应重放脚本。

### 不要触碰的对象

不要修改旧 `houdini-intelligence-agent` 仓库。

不要改 Houdini 安装目录、用户全局配置、已有用户 HIP、无关工作区改动。会改变场景的 smoke 必须使用专用测试场景；load/clear/replacement 测试必须有更明确的隔离和授权。

不要因为文件大，就重写 `ui/panel.py` 或拆出一套通用 UI framework。对 `runtime.py`、`ledger.py` 的修改必须由明确故障驱动，不能以“更优雅”为理由改变状态拓扑或持久化格式。

---

## B. 第一阶段：恢复可信 CI，修复小而明确的问题

### 工作内容

明确划分 backend tests 和 Qt tests。Backend 不安装也不导入 Qt；Qt job 真正安装依赖并运行 UI 测试，不能用 skip 代替。

修复 `BridgeError` 的冻结问题，保证异常能够正常经过 `contextlib`、unittest 和结构化 HTTP 错误路径。

保留当前少量跨平台、跨 Python 检查，不要扩展成庞大矩阵。真实 Houdini 支持范围应按实际 Houdini build 与其 Python/Qt 组合记录，不能从 `requires-python >= 3.10` 推导出所有 Houdini 版本都已支持。

### 完成标准

全新环境可以按正式 setup 路径运行检查；backend 不依赖 Qt；Qt 测试确实执行；原始 Codex 错误不会被异常包装错误覆盖。

### 推荐 semantic commit

```text
ci: separate backend and native Qt checks
fix(codex): preserve native exception propagation
```

这是两个不同语义边界，不要求强行合成一个提交，也不要为每个测试调整再产生一个提交。

---

## C. 第二阶段：修局部正确性和 Agent 使用成本

### Runtime 与工具契约

修复 `input_equals`：目标节点不存在时不能通过 `expected=None`。增加“目标不存在”“存在但未连接”“实际连接正确”三个小测试。

为 `views`、`checks`、`preconditions` 明确关键 schema 字段，尤其是 `view`、`kind`、`path` 及不同检查需要的字段。复用少量定义即可，不建设代码生成平台。

明确 `observe` 的语义：现实现会读取 before 和 after，因此不能让模型误以为它总能直接观察尚未创建的节点。新节点创建通常使用执行后 checks/readback；必要时再局部调整观察行为。

编译错误和 HOM 错误应保留安全、有界的定位信息，例如异常类型、脚本行号和简短原因。不要输出环境变量或完整敏感路径，也不要只返回无法修正的泛化错误。

### Panel 与异步边界

修复历史回填和已在途事件的衔接，覆盖：

* 回填开始前发出的 events 响应，在回填期间返回；
* 回填快照与实时 delta 重叠；
* 原生 `item/completed` 返回完整最终内容；
* 旧 Thread 的迟到响应不能覆盖新 Thread；
* 元数据可读、历史尚未物化时，不清空已有对话。

使用有界临时缓冲、明确的回调有效性或受控重同步；不要新增持久聊天日志。既不能漏事件，也不能把快照已有文字再拼一遍。

保留结构化错误分类，区分明确的提交前拒绝与未知提交。只有未知提交才进入“先 reconciliation、禁止盲目重发”。

**先修这些测试能证明的问题，再决定是否把某一组互斥 flags 收成小状态对象。**

### 完成标准

确定失败能直接给出可修正原因；不确定失败不会诱发重放；历史和实时消息不丢、不重复；Runtime receipt 不因 Panel 状态变化而被重新解释。

### 推荐 semantic commit

```text
fix(runtime): tighten targeted checks and tool contracts
fix(panel): preserve native events across history hydration
```

---

## D. 第三阶段：建立小型真实 Houdini 纵向验收

### 首个目标

先完成这一条链路：

> **Panel 输入 → 真实 Codex → MCP → Runtime → 主线程 HOM → 原生节点 → 定向验证 → receipt → Panel。**

不要先实现完整材质平台、渲染调度系统或者“支持所有 Houdini context”。

### 验收分两层，不能互相替代

**第一层：确定性的真实 GUI smoke。**

使用真实 Houdini、真实 `hou`、真实 `hdefereval`、实际注册的 `.pypanel` 和生产 MCP 路径。可以不调用模型，目的是先验证运行与执行链。

**第二层：真实 Codex 自然语言任务。**

在第一层成立后，通过 Panel 发出自然语言，由 Codex 自己选择工具、生成 HOM，再验证实际场景。确定性 smoke 通过，不能替代这一层。

### 首个自然语言用例

```text
在 /obj 下新建一个唯一命名的 geo，里面创建一个 Box，
把 size 的三个分量都设成 2。
用一个 HOM 批次完成，并回读参数确认。
不要搜索资料，不要截图，不要保存 HIP。
```

预期首次工具路径为一次 context 加一次 execute；必要检查在 execute 内完成。记录真实观察到的调用数，不把期望值写成实测值。

### 核心验收集合

| 场景                | 必须证明的结果                              |
| ----------------- | ------------------------------------ |
| Panel 真实加载        | 实际 `.pypanel` 生成正确 QWidget，无脚本加载错误   |
| Box / 参数 / 连线     | 节点真实存在，参数真实改变，连接真实正确                 |
| 几何与属性             | 实际 cook 后读到几何和预期属性，不只检查节点名字          |
| cook failure      | 区分“修改已完成”和“检查失败”，不误报全部成功             |
| 响应丢失              | 原 operation ID 可查；副作用只发生一次；不重发脚本     |
| 同 ID 不同 payload   | 拒绝冲突，不产生第二次执行                        |
| 排队取消              | 被取消操作没有进入 HOM                        |
| 运行中 Stop          | 区分 Codex 停止、取消请求、HOM 实际终态；验证真实按钮是否可达 |
| HIP 同路径重载 / clear | 旧 epoch 操作被拒绝，且发生在 HOM 前             |
| Houdini 退出与重新启动   | 原未完成状态如实恢复为 cancelled/unknown，不自动回放  |
| viewport capture  | 真正返回 image content，Panel 可显示，帧恢复符合约定 |
| 参考图               | 图片确实进入 Codex 输入，而不只是传递一个路径字符串        |

这不是要求一次自动化全部项目。先跑通节点闭环，再增加高风险故障项；余下项目明确记为未验收。

### 长任务特别要求

不得使用任意后台线程执行 `hou` 来绕过 GUI 卡顿。

不得承诺所有 HOM 都能强制即时取消。

不得随意调用 `processEvents()` 掩盖长批次问题。

优先缩小有意义的执行批次、使用明确协作检查点，并测试原生可中断操作的实际表现。真正需要后台渲染时，再为该具体场景引入独立渲染进程，而不是提前搭一个通用 worker 平台。

### 测试产物

每次真实验收只需一个小报告，记录 commit SHA、Houdini/Python/Qt/Codex 版本、用例结果、operation ID、耗时和必要截图。

输出到 `.runtime` 的独立目录，不覆盖已有结果，不记录 token，不保存整份用户 HIP。

没有真实 Houdini 环境时，可以提交测试入口，但结果必须明确写 **not run**，不能写 passed。

### 推荐 semantic commit

```text
test(houdini): add a real GUI vertical smoke slice
```

首次真实执行中发现的生产缺陷，按对应语义修复；不要为了让 smoke 绿灯改成 fake。

---

## E. 第四阶段：重新设计 Launcher，而不是只换颜色

### 视觉方向

建议统一为：

> **“进入异界创作站”式的日系科幻工作室入口。**

以深夜蓝紫为环境底色，青蓝与珊瑚粉作为有限强调色；使用明显的视觉主区域、分层构图、少量斜切或不对称结构、工作室徽记，以及具有动画作品感的原创插画或抽象图形。

**不要把“深色背景 + 青色边框 + 一个多边形”当作二次元设计已经完成。**

视觉需要同时具有构图、身份、节奏和材质层次，而不只是主题色。

### 交互构图

主区域负责世界观和工作室身份，操作区域围绕当前 workspace 和“进入工作室”组织。

正常使用时，用户首先看到当前 workspace、选中的 Houdini 环境、可选 HIP 和清晰的启动按钮。Codex 路径等低频设置不应始终压过核心操作。

空 workspace 状态要主动引导创建，不要留一个占据大面积的空列表。

错误区必须稳定、可读、可复制；不能为了维持漂亮版式把错误折叠到用户找不到的位置。

### 技术约束

继续使用 PySide6。QPainter、自定义 QWidget 和 Qt 属性动画足以作为这次实现的起点；Qt 的属性动画本来就支持驱动 QWidget 等 QObject 属性，不需要引入 Web frontend。([Qt 文档][3])

静态背景和装饰尽量缓存；动画只重绘必要区域。空闲、隐藏、最小化时停止不必要动画。不要让用户为了看完入场动画而等待启动。

启动过程展示真实阶段，例如环境检查、启动中、Runtime 已注册；无法测量的过程使用不确定进度，不伪造百分比。

保留正常窗口管理、键盘焦点和高 DPI 行为。不要为了无边框拖动、定制系统菜单等附加设计，增加一套与产品价值无关的窗口框架。

### 视觉验收

需要查看真实渲染的窗口，不只审查 QSS。

至少审阅空 workspace、已选 workspace、启动中、环境缺失、长错误、较小窗口和高 DPI 状态。素材必须有明确授权或为原创；UI 不依赖在线下载素材才能打开。

此前草稿可以作为一个方向参考，但必须重新判断，不能因为已有代码就保留。

### Panel 的边界

Panel 不做同等程度的“游戏化”。

它只需要适度统一品牌色和字阶，优先改善停靠空间里的信息密度、对话阅读、Stop 可见性、审批与错误。当前 Panel 的最小尺寸是 590×630，应在用户真实 Houdini 布局中验证是否过于占空间，不能用离屏大窗口截图代替停靠体验。

### 推荐 semantic commit

```text
feat(launcher): redesign the native creative studio entrance
```

---

## F. 后续能力扩展顺序

完成上述闭环后，按真实交付物扩展，而不是按 API 分类扩展。

| 顺序 | 任务目标                              | 暂时不要做                 |
| -- | --------------------------------- | --------------------- |
| 1  | 小型程序化模型：节点网络、参数、属性、输出             | 通用资产生成框架              |
| 2  | 一组实际材质与灯光调整，并看见结果                 | 全面材质抽象层               |
| 3  | 小型 Solaris/USD 场景，Karma 输出一帧到明确路径 | 渲染农场与通用 job scheduler |
| 4  | 简单动画或模拟的代表帧检查                     | 全帧自动验收平台              |
| 5  | 带参考图的分阶段任务                        | 第二视觉模型或自主 RAG 系统      |

每增加一项能力，先问：**通用 HOM 加少量定向读取能否完成？** 能完成就先用现有工具，不急着新增 MCP tool。

---

## G. Git 主线与提交规则

保留公开 `main` 历史，不重建 baseline，不 force-push，不新增长期 develop/release 分支。

施工采用一个短期分支；已有草稿分支如何处理，由 Codex 在确认当前改动后决定。不要同时保留两个做同一任务的长期开发分支。

提交按真实语义分组；开发过程中尚未发布的临时提交可以在不影响他人工作的前提下整理，但不为了美观重写公共主线。

合入方式选一种简单方式即可：干净的语义提交可以线性合入；确实属于一个整体的工作可以 squash。不要把 CI、异常修复、Launcher、Houdini smoke 全挤成无法定位的一个“final fix”，也不要为了形式拆几十个 PR。

`AGENTS.md` 中一次性的人员分工、强制多 worktree、指定某轮模型等说明，应由 Codex核对后移出永久开发规则。永久规则保留产品目标和安全不变量即可，不应让上一轮施工流程变成下一轮架构约束。

---

## H. 本轮停止条件

本轮做到以下程度就应收口：

**CI 可信；已确认的局部问题有回归测试；真实 Houdini 节点闭环通过；真实 Codex 能通过 Panel 完成简单任务；Launcher 达到实际视觉验收；尚未验证的能力被明确列出。**

不以“还有代码能重构”为理由延长工作。

也不以“单元测试全绿”为理由宣布所有 Houdini 能力完成。

**这次 Studio 最值得继续保持的，是它已经开始围绕场景事实而不是基础设施本身组织系统。接下来应让真实作品和真实操作决定代码增长，而不是让架构愿望决定产品方向。**

[1]: https://www.sidefx.com/docs/houdini/hom/hou/FlipbookSettings.html "https://www.sidefx.com/docs/houdini/hom/hou/FlipbookSettings.html"
[2]: https://openai.com/index/unlocking-the-codex-harness/?utm_source=chatgpt.com "Unlocking the Codex harness: how we built the App Server | OpenAI"
[3]: https://doc.qt.io/QT-6/qpropertyanimation.html?utm_source=chatgpt.com "QPropertyAnimation Class | Qt Core | Qt 6.11.1"
