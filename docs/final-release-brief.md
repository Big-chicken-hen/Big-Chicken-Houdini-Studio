# 1. Release 最终状态：**GO after bounded fixes**

**批准把 PANEL-STEER-1 纳入首发。**这项决定替代上一轮“放到 post-release”的安排；除此之外，不增加新的首发功能。

首发剩余工作固定为：

> **修稳 R4-NET-1 → 接入 native steer → 重建最终 RC → 完成标准用户安装验收 → 合并 #14 → 发布。**

本次重新读取的状态没有变化：`main` 为 `b48ceae…`，PR #14 仍是 Draft，head 为 `d2a727f917ab4ce596d8a7ace1059af55d1d9f39`；该 head 的 CI 已成功，但 NET-1 仍登记为已复现、未关闭，steer 仍只是待审批提议。

## 只保留三项首发门槛

| 门槛                | 当前判断                                              |
| ----------------- | ------------------------------------------------- |
| **R4-NET-1**      | 真实 correctness blocker。历史存在却加载为空且反复发生，不能当作普通限制带出去 |
| **PANEL-STEER-1** | 本轮正式批准的唯一新增首发能力。必须通过同一 Turn 追加输入、竞态和恢复验证          |
| **最终安装后验收**       | 一次 Windows 11 x64 标准用户完整链路，包含中途引导、重开续作和数据保留       |

**不再把 TC1 效率门槛、更多工具采用率、额外 UI polish、动态背景或更广平台支持加入首发 gate。**

本次审查读取了实际代码、固定 Codex 版本的协议、请求处理实现和原生测试；没有修改仓库，也没有代替 Codex 运行测试或 Houdini。

---

# 2. PANEL-STEER-1 最终审批

## 2.1 决定：首发前实现，现有 native API 足够

这不是需要 Studio 自己模拟的能力。

固定 **Codex 0.153.4** 已提供：

```text
turn/steer
  threadId
  expectedTurnId
  input
  clientUserMessageId（可选）
```

成功结果是：

```json
{"turnId": "原来的活动 Turn ID"}
```

原生处理路径明确区分 `Steered` 和 `NotSubmitted`；steer-only 路径不会创建新 Turn。没有活动 Turn、预期 ID 不匹配、不可引导的特殊 Turn 等情况会拒绝。

另外，固定版本的原生测试已经覆盖：发送 `clientUserMessageId`，随后对应的 `userMessage` 通过 `clientId` 回显这个标识。**这正好可以用于确认原发送，而不必比较消息文字。**

因此，本轮选择：

**直接接入 native `turn/steer`；不升级 Codex，不建立第二套消息队列，不引入 planner，不改 MCP Tool Surface。**

---

## 2.2 当前 Studio 需要修改的不是只有 Send 按钮

实际实现存在四个需要同时处理的接入点：

| 当前实现                                              | 对 steer 的影响                         |
| ------------------------------------------------- | ----------------------------------- |
| Protocol allowlist 没有 `turn/steer`                | 必须增加固定版本契约                          |
| Bridge 的 `_start_turn()` 拒绝 running 状态            | 需要独立的 steer 接纳路径，不能简单放松 start       |
| Composer 将 Send 和 Stop 放在互斥的 action slot          | working 时必须让两者独立存在                  |
| `submission_in_history()` 从“上一 Turn 之后”查找消息，并比较正文 | 无法正确确认同一 Turn 内的新引导，也无法稳妥处理相同文本连续发送 |

此外，现有 `sent()` 会设置 Turn ID 和 running 状态；这不能原样用于 steer，否则迟到的成功回应可能把已经完成的 Turn 错误“恢复”为 running。

**施工必须覆盖这四处，但不重写整个消息系统。**

---

## 2.3 Send 路由：一次点击只确定一种意图

产品规则定为：

| 点击时的可信状态                         | 行为                                  |
| -------------------------------- | ----------------------------------- |
| 当前 Thread 空闲，符合现有新任务接纳条件         | `turn/start`                        |
| 当前 Thread 有明确的、可引导的活动 Turn       | `turn/steer`，绑定该 Turn               |
| `turn/start` 尚未确认，活动 Turn ID 还未知 | 保留输入，短暂等待身份确认，不猜 ID                 |
| 正在 Stop，或当前发送结果/Turn 身份未确认       | 保留输入，先核对原状态                         |
| Codex Turn 已结束，但 Houdini 原操作仍运行  | 不假装存在可 steer 的 Turn；保留草稿，沿用现有操作收口逻辑 |
| Native 明确拒绝该类 Turn 的 steer       | 显示原因，保留输入，不改走其他接口                   |

**关键决定：路由意图在点击时固定。**

用户点击的是“追加到 Turn T”，即使请求到达 Bridge 时 T 已结束，也不能自动把它改成 `turn/start`，更不能发给后来出现的 Turn U。

反过来，用户按空闲状态点击正常 Send，也不能因途中状态变化，悄悄把它变成另一项任务的 steer。

Bridge 负责重新校验；native `expectedTurnId` 负责最后一道活动 Turn 匹配。**不需要每次先读取完整 history，更不需要额外 `hia_context`。**

---

## 2.4 Race fallback：保留内容，明确未发送，不自动续一轮

### 情况 A：Turn 已结束或 ID 已变化，native 明确拒绝

显示：

> **原任务已结束，这条引导没有发送。内容已保留；再次发送将开始下一轮。**

如果是另一个 Turn 已经活动，则说明“当前任务已变化”，让用户重新确认当前目标后再次点击。

**没有任何自动 fallback。**新一轮必须来自用户新的明确点击，而不是异常处理里的第二次 API 请求。

固定版本对“无活动 Turn”和“ID 不匹配”返回的是带说明的 invalid-request 错误，相关 `data` 并不都具有独立的稳定原因字段。应保留原生错误，并做局部、版本化的映射；不要虚构 native error code，也不要把所有 RPC 错误都视为“肯定未提交”。

### 情况 B：native 可能已接纳，但回应丢失

标记：

> **这条引导的接纳结果尚未确认；原内容已保留。**

核对原请求的迟到回应，或同一 Thread/Turn 中匹配 `clientId` 的 native item。**没有查到，不等于没有发送。**

当前 `CodexStdioClient.request()` 超时后会移除 pending request；新功能需要对原发送保留有限的迟到结果关联，不能超时后就只剩一个无法核对的错误。

这里要特别区分：

**`clientUserMessageId` 是关联标识，不是已经证明可安全重放的幂等键。**即使使用相同标识，也不自动重发。

### 情况 C：成功回应晚于 `turn/completed`

确认这条引导已被 native 接纳，但保持 Turn 已完成的状态。

**接纳状态与 Turn 运行状态分开更新。**成功 ACK 不能复活 Turn，不能撤销 Stop，不能恢复 Runtime owner。

---

## 2.5 Multiple steer：允许连续追加，不限制“每轮一次”

**批准同一长 Turn 中多次 steer，不设人为次数配额。**

为保持顺序，本轮采用最小的发送并发边界：

> **同一 Thread 同时最多有一条“接纳结果尚未确定”的用户发送。确认接纳后即可发送下一条，不等待整个 Turn 完成，也不要求先看到模型回应。**

这不是“每轮只能一次”，也不是排队等到下一轮。它只是把短暂的提交确认串行化。

快速双击或另一 Panel 同时提交时，未接纳的那份内容仍留在各自草稿中；Bridge 在转发前拒绝冲突，不替用户建立隐藏发送队列。两条合法、文字完全相同的引导使用不同消息 ID，不能按内容去重。

接口与实现没有体现“一次性 steer”限制；多次接纳的顺序与消息回显，仍必须在本次固定版本集成测试中实际验证，不能只凭 schema 宣称已经通过。

---

## 2.6 Thread、模型设置和草稿

**保留当前“活动任务期间不切换执行 Thread”的边界。**本轮不增加多 Thread 并行工作。

任务完成后正常切换；迟到回应只能结算原来的发送记录，不能写入新对话、清空新草稿或改变新 Turn 状态。

Steer 不调用 `thread/resume`，不重新绑定会话、不重置 consent，也不修改 model、effort、cwd 或 permission policy。原生 steer 本身不接受这些 Turn-level overrides。([OpenAI Developers][1])

现有文字、已经准备好的图片及有效选择引用可以继续使用，不扩展输入类型。图片能力以**正在工作的模型**为准，不拿“下一轮选择的模型”判断本次 steer。

每次发送冻结本次文本、附件与归属；用户可以继续编辑下一份草稿。回应只结算冻结快照，不能清空后来输入。

---

## 2.7 Stop / HOM / staged / approval 的边界

**Steer 是用户输入，不是操作取消，也不是执行器补丁。**

| 边界                            | 决定                                         |
| ----------------------------- | ------------------------------------------ |
| 已进入主线程的 HOM                   | 不修改、不回滚、不即时中断                              |
| 已接纳的 staged steps             | 不重写、不插入新步骤；需要停住时使用 Stop                    |
| 后续尚未决定的动作                     | 由 Codex 在后续推理中考虑新增要求                       |
| 正在等待的 approval                | 引导不等于允许、拒绝或撤销该请求；原审批继续保留                   |
| 已出现 partial / unknown receipt | 事实不变；活动 Turn 身份明确时，用户仍可发送文字纠偏              |
| Scene epoch                   | Steer 本身不写场景，也不刷新或绕过 epoch；旧选择引用不能伪装为当前选择  |
| Stop 与发送竞争                    | Stop 阻止尚未转发的 steer；已经转发的按真实结果结算，不自动重发或恢复工作 |

如果用户说“不要执行这个操作”，但该操作已经在等待授权，UI 应让其仍能明确拒绝该请求或点击 Stop。不能暗示“追加这句话已经撤销了那次调用”。

**不因 steer 增加全面 inspect、重新 context、强制 Stop 或重新审批所有工具的模型规则。**

还要诚实保留宿主限制：长 HOM 占住 Houdini GUI 主线程时，Composer 的物理交互也可能延迟。Steer 改善可响应期间的持续指导；它不让阻塞中的 Qt 主线程瞬间可响应。不要通过 `processEvents()` 或后台 HOM 绕过这个边界。

---

## 2.8 Composer 的最终体验

保留原 Send，working 时旁边独立显示 Stop，不增加用户可切换的“Steer Mode”。

建议文案：

| 状态            | 轻量提示             |
| ------------- | ---------------- |
| 活动 Turn 可接收输入 | **补充要求将发送到当前任务** |
| 正在提交          | **正在发送引导…**      |
| Native 已接纳    | **引导已接纳**        |
| 明确拒绝          | **未发送，内容已保留**    |
| 回应未知          | **发送结果待确认**      |

“引导已接纳”只说明 native 收到了，**不是“修改已经生效”**。是否影响后续工作，由后续回复、操作及场景结果体现。

复用现有 `arrow-up` 和 `square` 图标，不新增资产。IME 选词 Enter 不触发发送；现有 Ctrl+Enter 与鼠标 Send 走同一提交路径，重复按键不重复转发。

---

# 3. R4 最终施工顺序

## 顺序确定：先修 NET-1，再完成 steer 的集成

两者共享 `Api` 回应交付、connection generation 和消息确认路径。NET-1 未稳定时直接做 steer，无法区分“native 未接纳”与“UI 又丢了一次回应”。

### 第一步：NET-1 局部收口

当前代码已经持有 reply 引用，并使用 `deleteLater()`；因此不能未经证据就宣布“多持有一个 Python 引用”是根因。

限定排查：

```text
Api / manager / reply 存活
→ finished / destroyed / cleanup 顺序
→ 数据复制与 callback 交付
→ history 成功、失败和 generation 校验
```

Qt 对网络对象线程归属和 reply 销毁有明确要求；修复继续遵循这些原生边界，不替换 Houdini 的 Qt。([Qt文档][2])

要求是：请求只终结一次；成功交付已读取的普通 Python 数据；失败不变成 `{}` 或合法空历史；关闭和重连后的旧回复不污染当前 Panel。

只读历史恢复最多做一次自动补读，之后保留明确的重试入口。写请求绝不因该恢复机制自动重发。`ICON_EVENT_UNAVAILABLE` 只有在证据建立因果关系后才进入修改范围。

### 第二步：native steer 与 Composer 接入

在同一 PR 中用独立语义 commits 完成协议、Bridge、发送确认和 Composer。NET-1 测试稳定后再进行端到端交互，不重写 R1 的整个 history reducer。

### 第三步：最终包与两层验收

先做固定版本的接口/竞态测试和真实 Houdini 中途引导；随后把包含 steer 的安装包用于**一次标准用户完整 RC 链路**。不再用旧包的证据替代新包。

### 第四步：Ready → merge → release

三个门槛通过后，PR #14 转 Ready、合并，发布同一份已验收字节的安装包。

**不再附加 Tool Capability、视觉重做或新的模型 benchmark。**若标准用户环境仍不可用，就冻结候选并保留该未测门槛，不用继续开发其他功能填充等待时间。

---

# 4. Launcher Dynamic Artwork：值得保留，明确发行后再做

**方向值得采用，推荐未来作为可选的 native GPU artwork layer，而不是搬入网页应用。**

KumengScreen 的 README 确认其使用底图、法线图、局部 UV 变形、风格化光照与后处理；同时明确这是针对具体插画调校的艺术近似，不是换一张图就能自动得到同样效果。可吸收视觉方法，不搬 React/Vinext、本地 HTTP 或浏览器运行栈。

未来优先评估独立 Launcher 内的轻量 `QOpenGLWidget` 等原生组件，上层仍为现有 Qt 控件；GPU 层延迟初始化、有限帧率，失焦/最小化停止，尊重 reduced motion，失败立即静态回退。不得影响启动、Houdini launch、文字对比度或低端设备可用性。原生组件也有初始化和显存成本，届时测量后再定预算，不预先宣称“几乎零开销”。([Qt文档][3])

**本轮只登记方向；不加依赖、不写 shader、不换素材、不改变安装包。**

---

# 5. Codex Final Execution Brief

## Role / 本轮授权

```text
Pro = 最终审批、风险判断、产品方向。
Codex = implementation、tests、真实 Houdini validation、
        commit、push、PR 与发行收尾。

本轮批准：
1. 修复 R4-NET-1；
2. 将 PANEL-STEER-1 纳入首发；
3. 完成包含 steer 的最终 RC 和标准用户验收。

本轮不新增其他能力。
```

本 Brief 替代此前将 PANEL-STEER-1 放到 post-release 的决定。

继续使用：

```text
Branch: codex/windows-release-package
PR: #14
Reviewed head: d2a727f917ab4ce596d8a7ace1059af55d1d9f39
```

开始前核对最新 head。保留原 `3150c15` 失败包、截图和 receipts，不覆盖历史 evidence。

---

## A. 先关闭 R4-NET-1

读取现有 `docs/acceptance-issues.md` 与 R4 失败记录，针对现有 `Api`、reply 生命周期和 history 交付修复。

必须做到：

**一次请求、一次终态交付。**先读取有效 reply 的数据和状态，再完成 cleanup，再交付上层；正常 teardown 不应变成当前会话故障。

**空历史必须由合法成功响应证明。**失效 reply、空 body、错误 payload、加载失败不能伪造“零条消息的正常会话”。合法新 Thread 的空历史仍然允许。

**保留已有内容。**刷新失败不清空 timeline 或草稿；首次加载失败显示明确失败状态。

**回调绑定 generation。**Panel 关闭、重连、Thread 变化后，旧回复不能更改新界面。

仅允许一次有界的历史只读恢复；不得重发用户消息、approval response 或 Houdini mutation。

临时诊断记录 request identity、thread affinity、finished/destroyed 顺序即可。不要记录凭证、完整消息和脚本，不建立新 telemetry。

旧复现路径在两个 fresh Houdini GUI 进程中验证，覆盖长历史、重连、关闭重开及原来的双 Panel 情况。保留正常轮询观察，不能用单次成功关闭间歇问题。比较 canonical 内容与 native history，不只比较可见 card 数量。

---

## B. 增加最小 native steer contract

在固定 `0.153.4` 的 protocol allowlist 与契约材料中增加 `turn/steer`、其参数、返回值和 `userMessage.clientId` 关联测试。

保留现有 `POST /turn` 用于 start；增加独立的：

```text
POST /turn/steer
```

它不是新的 MCP tool。

Bridge 输入至少包含：

```text
expected_thread_id
expected_turn_id
client_user_message_id
connection_generation
text
attachments（复用已有格式）
```

其中 connection generation 使用已有连接身份，不另造独立会话协议。

映射到 native：

```json
{
  "method": "turn/steer",
  "id": 123,
  "params": {
    "threadId": "原 Thread ID",
    "expectedTurnId": "点击时的活动 Turn ID",
    "clientUserMessageId": "本次发送的唯一 ID",
    "input": [
      {
        "type": "text",
        "text": "屋檐缩到 0.25 米，不要修改窗户。"
      }
    ]
  }
}
```

不要附加 model、effort、cwd、sandbox、developer instructions。图片复用已准备好的 `localImage` 和现有限制。

不使用 `thread/inject_items` 代替用户 steer，不使用可能隐式 start-or-steer 的自制 fallback。

---

## C. Send admission 与路由

Composer 根据已知 native 状态选择 start 或 steer，点击时冻结意图；Bridge 校验后只转发对应方法。

Steer 需同时满足：

```text
连接与账号绑定仍有效
expected_thread_id 是当前所属 Thread
expected_turn_id 与当前活动普通 Turn 匹配
没有已生效的 Stop
没有另一条接纳结果未确定的用户发送
```

**不以 Runtime 正忙作为禁止 steer 的理由。**partial receipt、等待正常审批，也不能单独阻止用户向明确活动的 Turn 补充文字。

如果是 native Turn 身份未知、上一次用户发送 unknown、正在切换连接或 Stop 已请求，保留草稿并先核对状态。

短暂发送串行化复用现有 action/admission 边界；不要持有 Bridge 状态锁等待整个 RPC。Stop 不得排在 steer ACK 后面才能执行。

同一 Turn 可以连续发送 steer 1、2、3；一次接纳确认后立即允许下一次，不等待模型回答或 Turn 结束。快速重复点击不排入隐藏队列；被拒绝接纳的内容留在草稿。

---

## D. 发送身份、结果与 unknown

为新 Composer 的 start 和 steer 都生成 `clientUserMessageId`，保留旧 start 调用兼容性。

本地记录最少包括：

```text
message ID
intent: start / steer
connection/account/thread 绑定
expected Turn（steer）
冻结文本、附件与草稿版本
是否已经转发
接纳状态
对应 native item（观察到后）
```

这是**未决发送记录，不是第二份聊天历史或自动发送队列**。已在 native history 确认后释放不再需要的本地载荷；跨 Panel/连接恢复需要保留的未决输入，可使用现有本地状态边界中的一份有限快照，不添加新数据库。

### 三种结果

| 结果              | 处理                                                    |
| --------------- | ----------------------------------------------------- |
| `accepted`      | native 成功回应且 Turn 匹配，或精确 `clientId` 的 native item 已确认 |
| `not_submitted` | 转发前本地拒绝，或固定版本明确的 native 接纳拒绝                          |
| `unknown`       | 已可能转发但丢回应、超时、进程中断或结果无法确认                              |

不能沿用“所有异常都 `not_submitted`”的 catch。必须保存“是否已转发”的事实。

对原 JSON-RPC request 增加有界的迟到结果关联。超时不能变成自动重发；同一 message ID 再次到达 Bridge 时只能查询/返回原记录或冲突，不转发第二次。

`clientId` 匹配必须包含 Thread/Turn/连接来源。相同文本不是身份；没有找到该 item 不是未提交证据。

**不要重用当前只搜索后续 Turn 的 `submission_in_history()` 逻辑来确认 steer。**

### 竞态规则

* T 结束后收到 steer：明确拒绝、保留输入，不自动 start。
* T 已被 U 替代：不发给 U。
* ACK 晚于 terminal：结算消息，不把 Turn 改回 running。
* Stop 后 ACK 到达：记录接纳结果，不取消 Stop、不恢复 owner。
* 连接重建或 Thread 切换：旧回应不能清空新草稿。
* 结果未知：保留输入和查询入口，不因 Turn 结束自动判成失败或重新发送。

只在异常恢复时查询已有 native 状态；正常每次 steer 不额外读取全 history 或调用 Houdini context。

---

## E. Composer 修改

拆开 Send 与 Stop 的互斥 slot：

**Send 保持原按钮和图标；Stop 在工作期间独立显示。**

工作中可输入并追加要求，无“Steer Mode”开关。加入轻量提示“补充要求将发送到当前任务”。

发送后冻结本次快照，用户可以继续写下一份草稿。回调只结算原快照：

* 新草稿为空时，明确拒绝的内容可以恢复；
* 新草稿已有内容时，保留两份，通过现有未发送/未确认区域提供恢复或复制；
* ACK 不得清空后写内容，不能把旧附件覆盖到新草稿。

Native ACK 与真实 userMessage 回显之间允许显示本地发送状态，但不能伪造一条已落 native history 的消息。收到 `clientId` 对应 item 后合并投影，避免重复显示。

保留原生 IME。选词 Enter 不发送；Ctrl+Enter、鼠标点击、按键 auto-repeat 都经过同一个发送接纳点。

Steer 路径不要调用现有会清除 `turn_id`、重置 turn settings 或绑定新 Turn 的 start UI 逻辑。模型设置显示当前运行值，本轮不允许借 steer 改模型或 effort。

活动 Turn 期间保持当前 Thread 切换限制；这不是本轮要扩展的多会话能力。

---

## F. Stop / approval / Runtime 不变量

不修改 `hia_execute_hom`、staged steps、operation ID、receipt schema 或 mutation 结果。

Steer 不自动：

```text
Stop
grant/revoke consent
回答 approval
刷新 scene epoch
执行 inspect
重建 context
重写已 accepted 的 staged payload
恢复 paused Runtime owner
```

新增要求影响 Codex 后续推理。已执行内容仍按原 receipt 记录；需要停止已接纳流程使用原 Stop/cancel。

普通 pending approval 不妨碍追加指导，但原审批必须保留。审批回应自身 unknown 时沿用已有不确定性保护，不通过 steer 绕开。

不为新交互增加 model-side checklist、节点限制或固定 workflow。保留当前精简 instructions。

---

## G. Tests：覆盖边界，不建新平台

| 测试组             | 必须覆盖                                                                |
| --------------- | ------------------------------------------------------------------- |
| 路由              | idle→start；active→steer；starting 无 ID；仅 Runtime 忙但无活动 Turn          |
| Native contract | 固定二进制成功返回原 Turn；clientId 回显；无活动/ID 不符/特殊 Turn 拒绝                    |
| Multiple        | 同一长 Turn 至少三次连续 steer；顺序保留；相同文本不同 ID；双击不重复                          |
| 确认              | ACK、native item、terminal 的不同到达顺序；丢 ACK 后精确关联；未知结果不重放                |
| UI              | working 时 Send 与 Stop 共存；IME；输入期间 ACK；附件；未发送内容恢复                    |
| 隔离              | A/B/A、旧连接、旧 history、删除/归档后的迟到回应                                     |
| Stop/审批         | steer 待确认时 Stop 不被阻塞；已请求 Stop 后不再转发；pending approval 不被暗中回答         |
| 场景可靠性           | 原 staged payload、receipt、epoch、partial/unknown 和 no-blind-replay 不变 |
| NET-1           | reply 生命周期、正常 teardown、合法空 Thread、失败保留旧内容及有界恢复                      |

Native mock/受控测试与真实模型/Houdini 证据分开标记。不要因为 mock 同一 Turn 成功，就宣称模型已在真实工作中收到指导。

---

## H. 真实 Houdini 交互验收

使用一份有墙体、窗户与屋顶参考轮廓的测试 HIP，原对象允许观察但禁止无关修改。

第一条自然语言任务：

> 根据现有轮廓做一个可编辑的屋顶，提供坡度、屋檐宽度和厚度控制，保留现有建筑内容，完成后检查形状。

在该 native Turn 仍活动时，通过正常 Composer 发送：

> 屋檐缩到 0.25 米，不要修改窗户。

接纳确认后，同一 Turn 再发送：

> 坡度改为 35 度，两侧一致，墙体也保持不变。

不告诉模型使用哪个节点，不要求额外全场景 inspect。若 Turn 恰好已结束，这次应成为**正确拒绝的竞态证据**，不能伪装成成功 steer。

成功标准：

**追加消息属于原 Thread、原 Turn；未产生第二次 `turn/started`；native history 各保留一次输入；后续工作实际考虑新增约束；原窗户与墙体保持；没有篡改此前已接纳的 HOM 或 staged 操作。**

补充一组受控竞态测试验证发送时 Turn 已结束、ACK 丢失及 Stop；不要向自然语言任务偷偷注入故障。

---

## I. Final RC / clean non-admin

修复与 steer 提交后重建唯一候选，记录 source commit、builder commit、build ID、依赖 lock 和安装器 SHA-256。

在**一个 Windows 11 x64 标准用户环境**完成：

```text
实际安装
→ 开始菜单 Launcher
→ 官方登录
→ 打开测试 HIP / Studio Panel
→ 自然语言任务
→ working 中至少一次成功 steer
→ 继续修改与视觉反馈
→ 保存、关闭、重开
→ resume 原 conversation
→ 继续编辑
→ diagnostics
→ 升级、卸载及用户数据保留
```

机器可以已有正常安装的 Houdini；不要求卸载其他开发软件，但必须证明产品不依赖开发 checkout、PYTHONPATH 或外部 Python/Node/Git。不得复制认证或擅自创建测试账户。

对长历史、中文输入、工具活动与恢复做实际检查。若最终环境还不可用，保持候选冻结与 PR Draft，不把未测项改成通过。

---

## J. Dynamic Artwork、CI 与发行收口

Dynamic Artwork 只记录发行后方向，不加入任何 shader、素材、Qt GPU 模块、WebEngine 或服务器依赖。

语义 commits 按实际改动组织，例如：

```text
fix(panel): correct reply lifecycle during history delivery
feat(codex): support same-turn steering with exact input identity
feat(panel): allow guidance while work continues
test(steer): cover ordered sends races and recovery
docs(release): record final steer-enabled RC acceptance
```

**Ready / merge gate：**

NET-1 真实包回归通过；steer 的固定版本、竞态和真实交互通过；当前候选 CI 通过；标准用户完整链路通过；未决发送不丢失，原有 execution reliability 没有退化。

**Release gate：**

发布同一份已验收安装器，hash 和源提交可追溯；支持矩阵、未签名状态及已知限制如实记录。不要合并后偷偷重打一个不同的包。

本次条件全部满足即可结束 R4、合并 #14 并发布公开预览版。**除非出现新的真实 blocker，不再开启下一轮能力、性能或视觉建设。**

[1]: https://developers.openai.com/codex/app-server/ "Codex App Server | ChatGPT Learn"
[2]: https://doc.qt.io/qt-6.8/qnetworkaccessmanager.html "QNetworkAccessManager Class | Qt Network 6.8.8"
[3]: https://doc.qt.io/qt-6/qopenglwidget.html "QOpenGLWidget Class | Qt OpenGL"
