**TC-3 改为：复杂 Houdini 流程的分阶段执行与定点续作。此前提出的渲染方向撤回，不进入本轮施工范围。**

这次要增强的不是“再多支持一种截图或材质查询”，而是：

> **让 Codex 能把一个复杂工程拆成可检查、可传递结果、可停止的步骤；已经确定的步骤一次提交，出错停在明确位置，后续修正不必重跑整个工程。**

但不建设通用 Workflow Platform，也不让插件代替 Codex 规划。**Codex 决定流程，插件负责准确执行和记录。**

以下是调整后的完整审批与施工方向。

---

# 1. TC-1 / TC-2 快速审批

## 当前没有需要立即整体返工的 blocker

最新读取的 `main` 仍是：

```text
1734b0861adb30ddf334fc945bcec7db759db22c
```

本次检查中，TC-1 的完整调用标识保护、TC-2 的执行后观察和 partial 诊断边界仍然存在。`observe_after` 没有被提前解析；部分失败后不会默认继续读参数值或 geometry；scene replacement 和取消会阻止后续反馈读取。

TC-2 的验证文档记录了真实 H22 GUI 下的取景、请求帧、相机与视口恢复检查。这支持技术集成，**不代表自然语言模型效果已经证明**；本次也没有独立复跑那些本地检查。

## `TC1-A1` / `TC2-A1` 不阻塞 TC-3

继续保留冻结的 candidate、fixture、prompt 与恢复步骤。以后不能拿 TC-3 的新 main 替代原实验候选，也不能用 TC-3 任务成功反向宣称前两项已经验收。

本轮沿用以下规则：

**技术可靠性是交付门槛；模型收益是另一项需要真实证据的结论。**

下次具备已授权模型运行条件时，优先执行已有实验。若实验暴露搜索排序、结果组织或 description 问题，限定修正；若暴露重复执行、错误场景写入等问题，阻塞受影响能力。不要自动把局部问题扩大成整个项目停工。

---

# 2. Approval + Conversation 管理结论

## 2.1 Tool approval：优先做小型修正，不重建授权架构

### 当前问题是什么

Studio 目前**主动把七个 MCP 工具配置为 `prompt`**，然后通过用户显式开启的 `SessionTrust`，代答符合条件的 native 单次审批。因此，native 层不断产生 approval request 是当前实现方式；但在会话授权已经正确开启和匹配后，普通工具调用不应持续要求人工点击。

已经确认两处值得处理：

**授权入口与单次审批脱节。**当前 MCP RequestCard 只有“允许本次／拒绝／取消”；“本对话授权”在另一个控件里。点击“允许本次”不会开启复用授权，授权开启前已经挂起的请求也不会自动被处理。

**请求关联条件过于保守。**`SessionTrust.match()` 要求“当前总共只有一个 in-flight call”。更准确的边界应该是：“当前审批只唯一匹配一个未处理的调用”。多个不同调用在途，不必然意味着当前请求无法唯一识别。源码确认了这个限制，但尚无本次用户运行 trace，不能把它直接认定为所有弹窗的根因。

### 决定

将它作为**高优先级体验阻塞项**，安排独立小 PR：

```text
codex/scoped-consent-usability
```

最小范围是：让授权入口明确、为未复用授权提供原因、修正可唯一关联但被误判为歧义的情况。**不是改成 `approvalPolicy=never`，不是授予 `danger-full-access`，也不是通过更换账号或关闭 native 安全机制消除弹窗。**

会话切换、账号变化、Bridge/runtime 重启、场景替换后需要重新授权，继续保留。已有代码就是按这些边界重置 trust。

还必须明确：**授权执行任意 HOM，不等于后端已经证明每段 Python 都安全。**清空场景、覆盖既有文件、大范围删除等仍需要针对具体影响的确认；不要用静态脚本猜测器虚构一个安全沙箱。

---

## 2.2 Conversation management：现在值得做，但独立小 PR

Studio 不是没有 conversation 能力。目前已存在 native `thread/list`、`thread/start`、`thread/read`、`thread/resume`，以及 workspace 校验和恢复模型设置；主要缺口是列表只请求前 50 项，没有完整 lifecycle 操作入口。

固定的 Codex **0.153.4** 已有 `ThreadDeleteParams`、`ThreadSetNameParams`，其列表 schema 也支持 cursor、标题搜索、归档过滤和排序。因此，这不是必须升级 Codex 或重建聊天数据库才能做的功能。

**批准独立小 PR：**

```text
codex/native-conversation-lifecycle
```

本次只暴露：分页列表、按最近更新排序、标题搜索、打开/继续、新建、重命名、归档/恢复、真正删除。

删除与归档必须分开。官方语义中，归档是移动原生历史到归档区域；删除是删除持久化 thread 及相关历史，可能包括其派生子对话。具体运行行为仍以固定版本的 schema 和隔离验证为准。([OpenAI开发者][1])

**不做**全局聊天搜索数据库、跨 workspace 搬迁、分叉树 UI、自动摘要、完整历史分页重构。

它可以同周期推进，但不是 TC-3 的前置依赖。主要研发资源仍进入下面的复杂流程能力。

---

# 3. 当前最大的 Tool Capability 缺口

## 结论：缺少介于“单次语义脚本”和“整个复杂工程”之间的受控执行单位

TC-1 解决了较多“执行前知道什么”的问题，TC-2 解决了“执行后读回什么”的问题。

当前 `hia_execute_hom` 仍然接受**一个脚本**。Runtime 对这个操作调用一次主线程执行边界，最后提交整体结果；`checks` 在脚本完成后执行。

这意味着复杂工作通常落在两个极端：

| 做法               | 代价                          |
| ---------------- | --------------------------- |
| 每个语义步骤单独 execute | 已经确定的串行工作也需要反复往返，重复搬运路径与结果  |
| 多个步骤塞进一个长脚本      | 中间检查、步骤状态、部分成果和停止边界都要模型自行实现 |

**不是说现有工具不能做复杂工程。**它已经能执行任意 HOM，模型当然可以自己写循环、断言和中间结果。问题是：每次复杂任务都要重新编写这些稳定、重复的执行结构。

例如：

> 输入整理已经完成；模块分布已经完成；几何装配也成功；参数化检查失败。现在应修改参数连接，而不是重新采样、重新分布、重新装配。

目前 receipt 能说明脚本 completed/partial，但**没有原生的步骤级事实，告诉模型哪些阶段已经独立完成、哪些检查阻止后续继续**。当前 ledger 提供的是 operation 级记录。

## 为什么现在优先

这块能力直接服务于程序化资产、复杂网络搭建、批量属性处理、HDA 参数化、文件交付等流程，不绑定某个节点或渲染领域。

但它也有明确边界：

> **只有已经确定的连续步骤，才适合一次提交。需要看图、重新选工作流或解释异常时，必须交回 Codex 判断。**

不把“复杂流程”错误理解成“让 backend 自动决定接下来做什么”。

## 七个工具的下一步处理

| Tool                 | TC-3 决定                                 |
| -------------------- | --------------------------------------- |
| `hia_context`        | 保留，不再扩充默认上下文                            |
| `hia_inspect`        | 保留；复用已有 batch、view 和 metadata           |
| `hia_lookup`         | 保留；让模型继续查询当前安装，不扩大知识系统                  |
| `hia_execute_hom`    | **新增有限的 staged execution 输入模式**         |
| `hia_capture`        | 保留，作为流程之间的显式视觉检查                        |
| `hia_operation`      | **扩充步骤进度与步骤结果查询**，不增加 retry/resume 执行入口 |
| `hia_project_memory` | 保留，不参与执行状态存储                            |

本次不新增第八个工具，因为新增能力仍是“执行 HOM”及“读取原操作结果”，现有边界能清楚表达。

---

# 4. TC-3 阶段定义

## 阶段名称

**TC-3 — Staged Authoring / 复杂流程分阶段执行与定点续作**

## Goal

让 Codex 可以提交一段**有限、顺序明确、有检查门的多步 Houdini 工作**：

> 每步执行一次，完成后留下可靠记录；只有声明的检查和反馈条件满足才执行下一步；失败、取消或场景变化时停住；Codex 根据已有结果进行局部修正和后续工作。

这里的“续作”是**读取原事实后提交新的针对性操作**，不是断线后自动重跑原流程。

## User value

直接支持这样的完整工作：

> 从既有输入出发，完成数据准备、布局、几何生成、参数连接、输出组织和资产封装；其中某一段失败时保留前面成果；下一轮继续编辑原网络。

本阶段不承诺一段调用完成任何复杂任务，也不保证模型自动选择最优算法。它提供的是更好的执行组织和失败边界。

## 主要变化

| 层面    | 变化                                            |
| ----- | --------------------------------------------- |
| Input | `hia_execute_hom` 支持原 `script` 或新的 `steps`，互斥 |
| 数据传递  | 步骤间只传有限 JSON 结果，不传 live HOM 对象                |
| 执行    | 每步独立使用原有主线程执行边界，步间返回事件循环                      |
| 检查    | 当前步骤失败或声明检查不通过，后续步骤不执行                        |
| 收据    | 同一个 operation ID 下记录已完成、当前、未执行步骤              |
| 修正    | 读取原操作与现场后，新建局部修正操作；不提供盲目重放                    |
| 视觉    | 在需要视觉判断的边界结束当前批次，显式调用现有 capture               |

## Scope 与 non-scope

**做一个线性、有限的步骤执行器，不做 DAG 平台。**

本阶段不增加条件分支语言、嵌套流程、自动重试、自动补偿、跨进程续跑、持久化 Python 会话、全场景快照、后台规划器或第二模型。

不扩展 renderer、MaterialX、Solaris、simulation 专项；不做 TC-1 的第二轮重构。

## 新 API 与旧 HIA 的取舍

继续使用当前单一 Runtime。现有生产分发器是 `hdefereval.executeInMainThreadWithResult`，不需要换成另一套执行权。

当前 HOM 也提供一次性的事件循环回调；只有在真实 H22 验证发现现有分发方式不能提供合适步间边界时，才采用这种小型原生机制。不要在长脚本中调用 `processEvents()` 冒充安全分段。([SideFX][2])

H22 的 `asData()` / recipes 可以辅助某些具体 authoring，但序列化不等于步骤检查、可靠执行或失败恢复；本轮不把它们改造成新的执行 DSL。([SideFX][3])

也不迁移 MCP Tasks。当前 Tasks 扩展需要客户端显式支持，本项目已经有 durable operation；引入第二套任务生命周期不能解决这里的步骤语义，反而会扩大范围。([MCP Tasks Extension][4])

旧 HIA 只参考复杂 authoring、验证与失败案例，不搬其大型 executor、snapshot、context-pack 或知识库架构。

---

# 5. Codex Execution Brief

## Role

```text
Pro = 审批、工具方向、review。
Codex = implementation、tests、真实 Houdini validation、
        commit、push、PR。

Pro 没有修改仓库，也没有运行本轮测试或 Houdini 验证。
```

**本 Brief 替代此前提出的渲染方向。TC-3 的唯一主目标是复杂流程分阶段执行与定点续作。**

---

## A. Branch / PR

主分支：

```text
codex/staged-authoring
```

从最新 main 创建。本次审查基线：

```text
1734b0861adb30ddf334fc945bcec7db759db22c
```

单一 PR 目标：

> 在已有 execute/receipt 边界内支持有限多步 authoring，提供检查门、步骤级结果和可控停止，减少已知串行流程中的机械往返。

主要修改范围：

```text
mcp.py / tool_schema.py
scene.py
runtime.py
ledger.py 的最小必要扩展
observation_results.py
instructions.py
对应测试和验证记录
```

允许提取一个小型内部 staged-execution 模块，但不要建立另一套执行服务。

**TC-1 / TC-2 不得重复重做：**安装发现、help、parameter metadata、inspect batch、`observe_after`、partial 诊断、target capture 和已有恢复语义全部复用。

---

## B. `hia_execute_hom`：双输入模式

### 旧模式

保留当前单脚本请求及其语义。小型修改不需要被迫套入 staged mode。

### 新模式

新增：

```text
label: string
inputs: JSON object，可选
steps: Step[]，2–8 项
```

`script` 与 `steps` 互斥。新模式不接受含糊的顶层 checks/observe；它们属于具体步骤。

每个 Step：

| 字段              | 含义               |
| --------------- | ---------------- |
| `id`            | 当前请求内唯一的稳定步骤标识   |
| `label`         | 简短的人类可读目的        |
| `script`        | 一个可审查的语义步骤       |
| `preconditions` | 复用现有检查定义，执行前读取   |
| `checks`        | 复用现有执行后检查        |
| `observe`       | 复用既有目标的严格前后观察    |
| `observe_after` | 复用 TC-2，包括本步新建目标 |

限制为：总脚本文本不超过现有 256,000 字符；每步观察数量使用有界上限，建议不超过八项。不要用八个巨型脚本绕过原有请求预算。

**整个请求的 schema 与所有脚本语法，在第一步 mutation 前完成验证。**后面步骤存在语法错误时，不能先执行前面的写操作。

但不得预先解析未来才会创建的节点，也不得为了预检而执行脚本。

---

## C. 步骤间数据传递

每步获得独立 Python namespace，保留：

```text
hou
result
checkpoint()
cancel_requested()
output_path()
```

新增两个有限数据入口：

```text
inputs       本次请求的输入 JSON
results      前面已成功通过检查门的步骤结果，按 step id 索引
```

例如，下游脚本可以读取：

```python
source_path = results["prepare_inputs"]["output_path"]
source = hou.node(source_path)
```

上例只说明数据访问方式，不代表 `source` 的存在和内容已经永久保证。下游仍需当前步骤的 preconditions 或显式读取。

**数据规则：**

只传 JSON 标量、数组、对象；不传 `hou.Node`、Geometry、函数、模块或 pickle。每步输出最多 16 KiB，累计传递数据最多 64 KiB；过大或非 JSON 结果明确失败，不截成字符串继续执行。

无输出可以是 `null`。未声明检查不等于“已验证正确”，结果里必须保留这种区别。

传递的是验证后的完整数据，不是展示摘要。脱敏结果和截断摘要不得反向作为自动恢复输入。

不把临时变量注入 `hou.session` 来维持隐藏状态，不建立跨调用 Python 会话。

---

## D. 执行与检查门

### 调度方式

一个 staged 请求仍然只占用**一个 operation ID 和现有队列的一项**。

现有 worker 顺序推进步骤；**每步单独进入主线程 callback，结束后退出 callback，再决定是否推进下一步**。不要在同一个主线程 callback 中循环执行全部步骤。

其他 Studio 场景操作仍保持队列顺序，不能与这组步骤交叉写入。GET receipt 和取消不应依赖当前 HOM 步骤完成。

不得在主线程回调内递归调用 Runtime HTTP 来提交下一步，不新增第二个 worker 或执行 authority。

### 每一步必须遵循

```text
确认 parent operation 尚可执行
→ 确认 runtime / scene epoch / Stop 状态
→ 持久化本步即将开始的记录
→ 本步 preconditions 与严格 before-observation
→ 执行本步一次
→ checks / observe_after
→ 验证结果数据
→ 持久化本步结果
→ 决定是否进入下一步
```

下一步必须等待本步结果可靠提交。保存结果失败后停止推进，不允许“虽然 receipt 没存好，但工作继续了”。

### 默认检查门

出现以下任一情况，**后续步骤不执行**：

* 脚本异常或执行状态不确定；
* 任一声明的 check 不通过；
* 声明的执行后观察出现 error、partial 或 skipped；
* 步骤回传值不符合 JSON/大小限制；
* 取消、owner Stop、scene replacement；
* 步骤记录无法可靠持久化。

正常 warning 可以作为事实返回，不自动等同失败。不得根据错误消息文本猜测某一步可安全重试。

原单脚本模式保持原有兼容性；“失败后不推进下一步”是 staged mode 的明确语义。

### 人工编辑与时间上下文

步间会允许 GUI 处理事件，所以不能宣称执行期间现场完全不变。

每步开始重新检查 epoch，并运行该步的 preconditions。frame 和 Take 等会影响解释的工作状态应在步间记录；如果在步骤之外变化，停止并返回上下文变化，而不是悄悄切回原值。

脚本自身有意修改 frame，可以在本步结果中确立新的交接状态。**普通参数、连接、几何变化仍依赖声明的前置条件，不建设全场景 revision watcher，也不声称检测所有人工改动。**

---

## E. Receipt / `hia_operation`

### 同一原操作下记录步骤

保留原有 operation 字段，增加有界步骤记录：

```text
mode = staged
active_step
completed_steps
stopped_at
stop_reason
steps[]
```

每步记录：

```text
id / label
state
mutation_outcome
checks_outcome
observation_status
error / failure_phase / script_line
value / value_status
timings
```

尚未运行的步骤明确标为 `not_run` 或 `skipped`，不得与执行失败混淆。

### 总体状态不能覆盖局部事实

| 情况                | 必须表达                           |
| ----------------- | ------------------------------ |
| 所有步骤完成且检查门通过      | 整体 finished，mutation completed |
| 前两步完成，第三步异常，后续未执行 | 整体 failed/partial；前两步仍是已确认完成   |
| 前两步完成后取消          | cancelled，但不能报告整体 `not_run`    |
| 全部脚本完成，最后验证失败     | mutation 可以是 completed，验证仍失败   |
| 当前步骤的执行或提交结果不确定   | 当前步骤 unknown；此前已确认步骤保留         |
| 重启发生在步骤之间         | 保留已有步骤事实，不自动继续剩余步骤             |

**运行中 crash 恢复必须处理新增步骤状态。**不能只把 parent 标成 unknown，却让内部 running step 看起来仍在正常工作。可沿用当前 ledger detail 结构做最小扩展，不新建 workflow database。

### 查询入口

保留 `get`、`detail`、`list`、`cancel`。

允许 `detail` 增加可选 `step_id`，直接返回某一步的原始有界详情；不提供 `retry`、`replay` 或自动 `resume` action。

运行中分页详情要避免拼接不同版本的数据：使用小型 result revision 标识检测变化，或明确只允许分页读取已封闭的 step/terminal detail。不能把不断变化的整个 JSON 按字符切片后让模型误拼。

### 定点续作

失败后的正确路径是：

> 读取原 receipt 与必要现场事实 → Codex 决定修正范围 → 提交新的局部执行或剩余流程。

不是从失败位置自动继续，更不是重新提交整个旧请求。

已完成步骤的 receipt 是历史事实，不证明对应节点此刻仍未被人工修改。因此续作前仍要做必要的当前观察。

---

## F. 为什么不把 capture 加入步骤表

本阶段不增加：

```text
step.kind = execute / capture / lookup / decide / ...
```

所有步骤都是语义 HOM 执行。需要视觉判断时，结束当前 staged 请求，调用现有 `hia_capture`，让 Codex 查看，再提交后续请求。

这样可以避免把一个小型执行升级变成通用 agent orchestration。

同理，不在步骤之间自动调用模型，不自动搜索未知节点，不自动调整失败脚本。

---

## G. Description / Instructions

修改现有 scene instructions，增加以下行为原则即可，不编写工作流百科：

**已知连续步骤可以合并提交。**例如输入整理、布局生成、几何装配、参数连接；每步仍应有明确目的和必要验证。

**未知决策不能预写成盲目流程。**需要探索节点、读未知参数、看图判断或等待用户确认时，先结束当前批次。

**阶段边界是成果边界，不是 hou 方法边界。**不要把每个 `setParm` 包装成一个 step。

**失败后保留成果。**根据原 step receipt 和当前现场修正，不用删除重建来隐藏失败。

**批次授权覆盖该批次的全部步骤。**撤销会话授权停止后续自动许可，但不撤回已经接纳的 staged 操作；中止已接纳流程使用 Stop/cancel。

各步骤可使用独立 Undo group。Undo 是用户操作便利，不是文件或整个流程事务；官方 HOM 的 Undo group 本身也只是把所包围的修改组合成一次撤销动作。([SideFX][5])

---

## H. 两个产品小 PR

### H1. Approval correction

在 `codex/scoped-consent-usability` 中：

完善现有授权入口，让 MCP 卡片能直接打开已有“本对话授权”说明。保持当前待处理请求仍由明确的单次回应处理，不偷偷代答授权前的旧请求。

为未复用授权返回有限原因码：

```text
trust_off
scope_changed
ambiguous_call
arguments_redacted
runtime_unavailable
unsupported_request
stop_requested
response_unknown
```

匹配改为从 in-flight calls 中寻找**唯一、未消费、server/tool/arguments 精确一致**的候选，而不是要求整个集合长度为一。重复的相同候选仍然歧义；脱敏后不能证明相等的参数仍然不自动允许。

保持 native prompt 策略、版本化 metadata 检查、账号/Thread/runtime/epoch 绑定与撤销边界。不要靠放宽未知 metadata 或匹配一段问题文本来“修好”授权。

测试必须覆盖：同一 Thread 连续多次工具调用、多个不同在途调用、重复相同调用、撤销、重启、旧请求、unknown response，以及 staged execute 的完整参数匹配。

**这个小修正优先收口，但不等待它完工才设计和实现 TC-3。**

### H2. Native conversation lifecycle

在 `codex/native-conversation-lifecycle` 中：

以固定 Codex 版本生成的真实 schema 为依据，增加 native 方法的最小 allowlist、Bridge 路由与紧凑 UI 入口。

本轮范围：

```text
thread/list：cursor、标题 searchTerm、archived、updated_at 排序
thread/start / read / resume：复用
thread/name/set
thread/archive
thread/unarchive
thread/delete
```

禁止另建会话数据库；搜索明确是标题搜索，不伪装全文搜索。

所有操作都校验 workspace 和目标 Thread。resume 后 model/effort 以 native 返回为准；draft、附件保持原 Thread 归属；consent 不从旧会话或重启前自动恢复。

删除必须有确认，并说明 native 删除可能影响派生子对话。运行中、审批结果未知、相关 Houdini 操作仍未结束时不删除当前会话。

只有 native 成功确认后才清理对应 Panel draft、选中状态和可证明仅属于该草稿的临时数据。**不要按 Thread 删除整个 workspace 的 receipts、captures、HDA 或输出文件**；它们目前并不等同于独占的聊天附件。

处理非当前 Thread 的 rename/archive/delete 通知，避免沿用“非当前 Thread 事件全部忽略”而让列表失真。使用请求 generation 防止晚到回调把已删除对话重新放回 UI。

未知响应先核对原生状态，不以“列表暂时没显示”认定删除成功。不能用隐藏列表项冒充 native delete。

此 PR 独立测试、独立合并，不拖入 TC-3。

---

## I. Tests：只对应新增风险

| 风险     | 必须验证                                               |
| ------ | -------------------------------------------------- |
| 混合输入   | script/steps 互斥，step ID 唯一，长度限制与各层校验一致             |
| 后段语法错误 | 第一处 mutation 前发现全部脚本语法错误                           |
| 数据传递   | 有效 JSON 可传递；live HOM 对象、超限值拒绝；不从摘要取输入              |
| 检查门    | check 或观察失败后，下一步骤执行次数为零                            |
| 原功能回归  | 单脚本、严格 before-observation、TC-2 partial 诊断保持        |
| 持久化    | 每步开始/结束记录先后顺序正确，提交失败不推进                            |
| 取消     | queued、步骤内、步骤间、最后一步结束时分别正确                         |
| 现场变化   | epoch、frame/Take、声明的参数或连接前置条件变化能阻止后续写入             |
| 断线与重启  | 原 ID 查询不重跑；已确认步骤保留，未知步骤不伪装完成                       |
| 摘要     | 每步状态、完整标识、停止原因保留；step detail 可正确读取                 |
| 主线程    | 每步单独 callback，步间事件有机会处理；没有后台 HOM 或重入 event pumping |
| 修正     | 新的针对性修正保留此前节点身份与用户编辑，不重跑已完成步骤                      |

不要为此建设通用故障注入平台。复用已有 fake HOM、Runtime、ledger 与真实 H22 驱动，补几个关键边界即可。

---

## J. Real Houdini Acceptance

### 技术验证：硬门槛

通过生产 Adapter → Runtime → 主线程队列，执行一个至少四步的真实流程，覆盖：

**输入处理、模块布局、几何生成、参数化及输出组织。**

验证原 operation 中逐步出现确认结果；步骤间 GUI 事件能够处理；Stop 到达后未开始的步骤不运行。

另做独立受控故障：前两步完成，第三步发生脚本异常或检查失败。确认第四步未执行，前两步节点与结果保留；Codex/测试驱动随后提交局部修正，而不是重放整个原批次。

丢响应、receipt 提交失败和重启边界使用最少必要案例覆盖。技术驱动与模型任务分开，不向自然语言任务偷偷注入故障。

### 自然语言任务：程序化步道资产的完整交付

准备专用 HIP，包含两条不同形状、有一定高差的道路引导曲线，几个已有铺装/路缘模块、排除区和无关保留资产。至少一个输入有非默认对象变换。**不预建目标生成器。**

第一轮：

> 利用场景里已有的道路曲线和模块，做一套可复用的程序化步道。需要可调路宽、铺装尺寸、接缝、路缘高度和随机种子；排除区内留出通行缺口。曲线或参数改变后，铺装和路缘要能继续更新。整理输出、UV 和稳定的部件标识，封装为可在另一条曲线上使用的 HDA，并保存示例工程到指定测试目录。保留原有输入和其他资产，不需要材质、灯光或渲染。

这里不指定节点，不指定步骤数量，也不向模型提供预期工具调用序列。

第一轮后，测试者修改原曲线和一个排除区，保留操作记录。

第二轮：

> 我刚修改了第一条曲线和排除区。请在现有资产上继续修改：把第二段步道加宽，并增加一个独立控制，让路缘高度不再随铺装厚度变化。保留我的修改、已有参数和稳定的模块变化。用第二条曲线验证它仍可复用，更新测试目录中的资产版本，不要删除重建整套工程。

版本更新写入明确的新测试输出，避免把“更新版本”变成擅自覆盖未知文件。

### 验收结果

检查的不是只有“网络无红错”：

* 曲线变化后铺装与路缘是否真实更新；
* HDA 参数是否确实驱动内部网络，而不是外观上增加几个无效控件；
* 排除区和第二条曲线是否有效；
* 节点网络是否可读、可编辑；
* 第二轮是否保留原节点、用户曲线修改和既有控制；
* HDA 在干净测试环境中是否可实例化，不依赖原 HIP 的隐藏路径；
* 文件是否实际创建，不能把 `output_path()` 返回位置当作交付完成。

HDA 封装仍通过原生 HOM 与现有 output policy 完成，不为这个验收新增“步道工具”或“HDA 专用 MCP tool”。

### 最小 evidence

记录 tool-call 类型与数量、staged 请求与 step 数、检查门失败、重复执行、修正范围、原 operation ID、关键节点身份、两轮 HIP/HDA、必要 viewport 图像，以及 fresh-load 结果。

**内部步骤不是额外模型 tool call；后台轮询也不是。**

收益判断重点是：已经确定的多步工作是否避免了不必要的逐步往返；出错后是否明确停住并保留成果；第二轮是否能在原工程上继续工作。不要预先宣称百分比提升。

---

## K. Git 与 Merge Gate

语义提交可以按实际改动组织：

```text
feat(execution): add bounded staged HOM authoring
feat(runtime): persist step outcomes and halt at failed gates
feat(operations): expose staged progress and step details
test(authoring): verify staged execution and targeted continuation
```

Approval 和 conversation 变更各自独立提交、独立 PR。不要把三个工作混成一个杂项大 PR。

### TC-3 技术合并必须满足

**全部满足：**

1. 新 staged contract 与旧单脚本模式兼容。
2. 每步执行、检查、结果传递与持久化次序经过验证。
3. 失败、取消或未知结果后不自动推进或重放。
4. 已确认步骤事实不会因为后续失败而消失。
5. 真实 H22 GUI 验证了步间执行边界及 Stop 行为。
6. 真实复杂网络流程和局部修正通过，原节点与用户内容保留。
7. 既有 receipt、epoch、TC-1/TC-2 与当前候选 CI 通过。
8. 没有扩大成新调度平台、第二智能体或渲染项目。

这次触及 Runtime 推进与持久化边界，**不能仅凭 unit tests 和 CI 技术合并**。

自然语言任务若仍因 official login 无法运行，可以登记冻结的 `TC3-A1`，但不得替代上述真实 Houdini 技术验证，也不得宣称模型效果通过。`TC1-A1`、`TC2-A1` 继续独立保留。

**执行顺序确定为：TC-3 主线开工；授权问题以最小修正优先收口；对话管理独立小 PR。核心产出是更可靠地完成复杂流程，不是增加更多外围界面或渲染功能。**

[1]: https://developers.openai.com/codex/app-server "https://developers.openai.com/codex/app-server"
[2]: https://www.sidefx.com/docs/houdini/hom/hou/ui "https://www.sidefx.com/docs/houdini/hom/hou/ui"
[3]: https://www.sidefx.com/docs/houdini/hom/hou/OpNode.html "https://www.sidefx.com/docs/houdini/hom/hou/OpNode.html"
[4]: https://tasks.extensions.modelcontextprotocol.io/specification/draft/tasks "https://tasks.extensions.modelcontextprotocol.io/specification/draft/tasks"
[5]: https://www.sidefx.com/docs/houdini/hom/hou/undos "https://www.sidefx.com/docs/houdini/hom/hou/undos"
