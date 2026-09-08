# 审批结论

**TC-1 的真实模型对照继续保留，但不应阻塞 TC-2 开发。**

本次明确调整上一轮的验收安排：**把“工具实现可安全集成”和“已经证明改善模型行为”分开审批。**前者可以先完成并合并；后者必须等待真实对照，不能用 CI 或后端检查替代。

**批准 TC-2：目标化执行反馈——让 Codex 在一次语义执行后直接获得结果事实，并能按工作对象取得正确的视觉反馈。**

主要修改 **`hia_execute_hom` 和 `hia_capture`**，复用 TC-1 的 inspection、结果摘要与现有 receipt。**不新增顶层工具，不再扩建 lookup，不重写 executor，不建设通用验证平台。**

本次读取的 PR #6 为 Draft，head 是 **`835e05b131bd5c23773838719f36ae482acb4ac6`**，base 是 **`1e9f0f4dc43465bd221b3e0832a5e75d6cd1aa66`**。我已读取相关实现、schema、测试与验证记录，并核对该 head 的 CI；没有修改仓库或运行测试、Houdini。

---

# 1. TC-1 快速审批

## 1.1 设计方向通过，但有一个应在 #6 内修正的收口问题

**没有发现需要推翻 TC-1 设计、停止后续开发的 blocker。**

当前实现已经落实了安装目录搜索、类型状态、本地 help、参数模板与实例区分、局部批量失败隔离，以及严格执行前观察。不是只修改了工具 description。

但是，**`observation_results.py::_shrink()` 会截短调用标识。**其 `IDENTITY` 包含 `path`、`name`、`type_name`、`parent` 等字段，超过 256 字符就把原值替换成前缀；其他连接路径也可能被通用字符串裁剪处理。虽然有 `*_truncated` 标记，但这些字段承担的是后续调用地址，不应退化成展示用前缀。当前摘要测试使用的都是短路径，没有覆盖这个边界。

**处理决定：在 #6 增加一个小型修正和针对性回归。**

保留完整节点路径、类型身份、连接源路径、参数标识与分页定位字段；优先删减 help、说明及记录数量。极端情况下宁可明确省略记录并提供 detail 入口，也不能把不完整地址放回可执行字段。

这是 **#6 合并前的修正项，不是 TC-2 开工前的等待项**。

## 1.2 当前证据能支持什么

| 证据层         | 现在可以依赖                                                               | 现在不能宣称                      |
| ----------- | -------------------------------------------------------------------- | --------------------------- |
| 源码与受控测试     | 查询分支、分页、局部错误、默认不求值、执行前失败拦截等已经实现并有测试覆盖                                | 所有真实 HIP、所有 HDA、所有异常组合都正确   |
| CI          | 当前 head 的四个 backend matrix job 和 native-ui job 成功                    | 真实模型已经更会使用 Houdini          |
| 真实 H22 后端记录 | 验证文档记录了内置 ZIP help、HDA help/alias、实际端口、multiparm、非默认对象变换下的 bounds 检查 | 我独立复跑了这些检查，或这些检查证明 GUI 视觉结果 |
| 尚未执行的模型对照   | 实验输入、fixture、计数与恢复步骤已准备                                              | 调用减少 20%、工作流更现代、人工修改后续编更可靠  |

真实 H22 原始报告保留在本地；本次读取的是仓库中的版本化验证说明，而不是独立复跑结果。验证文档明确承认模型实验未执行，这个表述应继续保留。

## 1.3 不阻塞下一阶段，且允许条件式技术合并

**批准以下顺序：**

> 修正 #6 的标识截断问题，补回归并通过当前候选 CI
> → 将模型对照登记为明确的 deferred acceptance
> → #6 可以技术合并
> → TC-2 继续实施，不等待对照结果。

这里正式替代上一轮“完成完整配对实验才能合并 #6”的要求。**TC-1 可以标记为“实现已集成、行为收益待验证”，不能标记为“效果验收通过”。**

Deferred acceptance 以 **`TC1-A1`** 保留，负责人是 Codex，至少固定：

* 原基线 SHA、最终 TC-1 候选 SHA、fixture 与两轮原始 prompt；
* 相同 Houdini、Codex、模型及 effort 的比较条件；
* 当前阻塞原因、已有恢复步骤、原始证据位置；
* 完整失败记录，不只保留成功样本。

**必须用冻结的 TC-1 候选做对照，不能以后拿“TC-1＋TC-2”冒充 TC-1 单独效果。**

在下一次可进行已授权模型运行时优先执行；TC-2 review 必须报告 `TC1-A1` 状态。若仍被登录条件阻塞，就继续标记 pending，不能移除或伪造完成。

后续对照若只是收益不足，优先限定在搜索排序、结果组织和 description 内修正；若暴露错误地址、错误状态或副作用可靠性缺陷，则阻塞**受影响能力**的交付。不要因此自动重写已经验证的 runtime，也不要冻结所有工具开发。

---

# 2. 当前剩余最大的 Tool Capability 缺口

## 结论：模型更容易知道“该怎么做”了，但“做完以后得到什么”仍然不够直接

TC-1 补强的是行动前的信息。当前最值得补的是行动后的反馈链：

> **执行一个建模步骤 → 读回实际输出 → 看见正确对象 → 决定继续修改还是局部修正。**

这不是再增加一个“验证节点存在”的工具。

## 2.1 全部工具的当前判断

| Tool                 | TC-1 之后的判断                               | TC-2 决定            |
| -------------------- | ---------------------------------------- | ------------------ |
| `hia_context`        | 工作入口已经足够明确；继续塞信息的边际收益下降                  | 保留，不扩展             |
| `hia_inspect`        | 已有可复用的局部观察能力；问题更多是调用时机与执行后的接入            | 复用实现，不再重做 contract |
| `hia_lookup`         | 本轮安装发现主体已经交付；下一步先观察实际模型使用情况              | 冻结功能范围，只修确认缺陷      |
| `hia_execute_hom`    | 能做语义批次，但新建目标的标准回读和失败后现场反馈仍有缺口            | **主升级对象**          |
| `hia_capture`        | 能可靠截图，但目标仍由当前 viewport 和调用者提供的 bounds 决定 | **主升级对象**          |
| `hia_operation`      | 原操作查询与不重放语义正确                            | 保留，仅让新增结果可以正常查询    |
| `hia_project_memory` | 不解决本轮主要 authoring 瓶颈                     | 不扩展                |

上述边界来自当前实际工具 schema，而不是按七个名字推测。

## 2.2 三个具体缺口

### 第一，新建目标仍然缺少统一的执行后观察入口

当前 `observe` 在脚本前后读取**同一组目标**。因此，新建节点不能直接放入它，否则前置读取就会失败；模型要么在脚本中自行编写 readback，要么再调用一次 inspect。

脚本内 readback 应继续支持，但不应成为获得标准 node、parameter、geometry facts 的唯一低往返路径。

### 第二，部分执行失败时，最需要的现场信息反而缺失

当前 `execute()` 捕获脚本异常后直接返回；正常路径中的 checks、after-observation 和 `result` 转换不会继续发生。因此，receipt 能正确说明“partial”，却通常不能直接说明：

> 哪些已声明的目标现在存在？哪些参数已改变？错误节点留下了什么诊断？

这不是 receipt 不可靠，而是**可靠地报告了不完整操作，却没有足够经济的下一步观察**。

### 第三，视觉反馈缺少“按工作对象查看”的 contract

当前 capture 没有 node target 或 viewpoint 参数；review bounds 需要调用者提供，而且使用当前方向。TC-1 虽然已经标明 geometry bounds 的坐标空间，但从局部 bounds 到正确 framing，仍然交给模型自行处理。

这会产生一类没有创造价值的 HOM 片段：找对象、算 bounds、转换空间、调整视图、截图、恢复。**其中稳定、重复且容易出错的部分，应由 capture backend 承担。**

此外，TC-1 的有用摘要只覆盖 context/inspect/lookup，execute/capture 的大结果仍使用旧的 16,000 字节退化路径。新的执行后反馈必须同时处理这个出口，否则增加的观察又会被藏进 detail。

## 2.3 为什么它比其他方向优先

这是一个跨建模、程序化装配和局部动画编辑都能复用的改进，不依赖某种具体节点。

相比之下，直接做 MaterialX/Solaris/Karma 专项，会立即进入 USD 绑定、渲染产物、图像格式与色彩解释等新的领域边界；继续扩 lookup 则容易在尚未观察 TC-1 使用效果前重复投资。

**本轮先让已有执行能力形成更强的反馈闭环，而不是同时新增四类领域工具。**

---

# 3. TC-2 方向

## 阶段名称

**TC-2 — Targeted Execution Feedback / 目标化执行反馈**

## Goal 与用户价值

完成后，Codex 应能：

> 一次构建或修改一个可审查的节点网络步骤，在原 receipt 中拿到指定目标的实际结果；遇到部分失败时获得有限现场诊断；按节点取得可复现的 review 图像，而不必先写一段临时视口准备脚本。

**不是把所有工具合并成一个万能调用。**Mutation 与视觉 capture 仍是两个清楚的操作边界。

## 核心交付

| 交付      | Contract / backend 变化                                            |
| ------- | ---------------------------------------------------------------- |
| 执行后定向回读 | `hia_execute_hom` 新增 `observe_after`，复用现有 view schema，允许读取本次新建目标 |
| 部分失败诊断  | 脚本已经进入执行后异常退出时，对声明目标进行有限、非求值式诊断；不自动 cook、不自动修复                   |
| 按对象截图   | `hia_capture` 增加节点 target 和少量命名视角，backend 处理目标解析、坐标转换与恢复         |
| 有用的执行结果 | 首屏保留 mutation、checks、observation 状态和实际记录；原 receipt/detail 继续有效   |

## Scope

以 **SOP/OBJ 几何工作对象**为视觉支持范围；执行后 views 仍复用现有通用观察接口。

每次 capture 仍只生成一张图。不同视角、不同帧是明确的独立请求，**本轮不增加多图批处理和自动截图**。

## Non-scope

不做新的执行 DSL、graph transaction、全场景 diff、自动依赖图、后台 worker、硬超时、自动 rollback 或 retry。

不做 render farm、Karma 渲染调度、USD primitive framing、自动材质评价、simulation 验证框架、整段动画录制。

不做 Thread requirements、memory 注入、UI 改版、Codex 版本升级或 MCP 协议升级。

## 旧经验与新方案

旧 HIA 可参考“显式目标验证”“cook 与缓存证据分开”“截图与恢复错误分开”等经验，但不要搬它的大型 validation 和场景分类逻辑。旧代码已经包含相当复杂的验证遍历，不能因为存在就整体移植。

当前官方 HOM 已提供 viewport framing、stashed camera 和恢复接口；尤其 `defaultCamera()` 在 camera lock 下可能直接影响相机节点，因此 target capture 必须继续遵循先保存、解锁/脱离、临时观察、恢复的边界。([SideFX][1])

也检查了 H22 的 `asData()`/`parmsAsData()`：它们适合受控序列化，但不能代替这次所需的执行后事实和视觉验证，**不因此另造 recipe executor**。([SideFX][2])

现有 MCP 版本已经支持原生图像内容，这次不需要为视觉反馈升级协议或更换 Codex 集成方式。([Model Context Protocol][3])

## Completion criteria

源码测试、真实 H22 后端与 GUI 技术验证必须证明 contract 和恢复行为；一次自然语言两轮任务用于证明模型实际采用能力并持续编辑。

**模型端效果审批与技术合并继续分开；但涉及视口、相机、frame 恢复的真实 GUI 验证不得延期替代。**

---

# 4. Codex Execution Brief

以下内容可直接交给 Codex。

## Role

```text
Pro = 工具方向、审批、review。
Codex = implementation、tests、真实 Houdini 验证、commit、push、PR。

Pro 没有修改仓库，也没有代替 Codex 执行测试或 Houdini 验证。
```

批准实施 **TC-2：目标化执行反馈**。不要重新开启整体架构设计，也不要重复建设 TC-1。

## Branch / PR

**Branch：`codex/tool-capability-feedback`**

**单一 PR 目标：**实现执行后定向回读、有限失败诊断与按工作对象截图。

当前依赖 PR #6，head 为：

```text
835e05b131bd5c23773838719f36ae482acb4ac6
```

若 #6 尚未合并，从其固定 head 创建 stacked branch，TC-2 PR 暂时以 `codex/tool-capability-discovery` 为 base，清楚标注依赖。#6 合并后再 rebase/retarget 到 main。

TC-1 收口修正进入 #6，不混进 TC-2 的功能提交。不要把同一份 TC-1 实现重新复制或 cherry-pick 成第二套代码。

### TC-1 收口与 deferred acceptance

在 #6 修正摘要中的调用标识截断，增加长路径、长连接源路径与超预算 batch 的针对性回归。

更新治理文档，明确本次审批允许：

```text
TC-1 技术合并
≠
TC-1 模型效果验收通过
```

登记 `TC1-A1`，冻结原基线、最终 TC-1 候选、fixture、prompt 与执行条件。保持完整实验恢复步骤，不修改历史证据，不宣称达到原来的效率门槛。

完成该小型修正、相关测试和当前候选 CI 后，#6 可按本次条件式批准技术合并；无需等待 `TC1-A1`。TC-2 开发可同步推进。

---

## A. `hia_execute_hom` Contract

### Input

保留：

```text
script
label
preconditions
checks
observe
```

新增：

```text
observe_after: View[]
默认 []
最多 16 个 views
使用 TC-1 已有 view schema
```

示例是追加到现有执行请求中的字段：

```json
{
  "observe_after": [
    {
      "view": "node",
      "path": "/obj/shading_asset/OUT"
    },
    {
      "view": "parameters",
      "path": "/obj/shading_asset/controls",
      "pattern": "*angle*",
      "limit": 8,
      "include_values": true
    },
    {
      "view": "geometry",
      "path": "/obj/shading_asset/OUT",
      "samples": 0
    }
  ]
}
```

**`observe_after` 的目标可以由本次脚本创建。**输入校验只验证 request shape，不提前解析这些节点。

旧 `observe` 语义不变，仍是既有目标的执行前后观察。不得悄悄把它改成只在执行后读取。

### 正常执行顺序

```text
纯输入校验 / compile
→ 原有 preconditions
→ 原有严格 before-observation
→ 执行一次脚本
→ 原有 checks
→ 原有 after-observation
→ 新 observe_after
→ 结果转换与原 receipt 提交
```

在执行后的检查与观察之前，确认没有发生 scene replacement。不能在脚本切换 HIP 后继续把新场景当作旧场景读取。

### 执行后观察行为

每个 view 独立返回：

```text
index
path / view
status
实际数据或结构化 error
读取时 frame / scene_epoch
```

一个目标缺失不丢弃其他结果。一次 observation 失败不把已完成 mutation 改成“未执行”。

读值、geometry、checks 可能触发求值/cook，沿用 TC-1 的明确语义。不要为“确保新鲜”统一强制重 cook。

### 部分失败行为

只在脚本已经进入 `exec` 后异常退出时，对声明的 `observe_after` 目标进行有限诊断。

本轮采用固定规则，**不再增加一个复杂 failure-policy schema**：

| 失败后的 view                       | 行为                                         |
| ------------------------------- | ------------------------------------------ |
| `node` / `children`             | 读取有界结构和已有诊断，不强制 cook                       |
| `parameters`                    | 仅 metadata；即使请求 include_values，也明确标记值读取被跳过 |
| `parms` / `geometry` / `checks` | 跳过，返回原因，避免失败后意外求值或启动昂贵 cook                |

若已收到取消、发生 scene replacement 或无法建立安全读取条件，跳过剩余诊断并记录原因。

Compile、precondition、before-observation 阶段失败时，不运行 `observe_after`；mutation 继续是 `not_run`。

**不得自动修正、删除、重建或重放脚本。**

脚本失败前已经写入 `result` 的内容可以作为有界 partial value 返回，但必须明确它是“部分脚本回传值”，不是已经验证的最终结果。

### Result

继续保留原有：

```text
state
mutation_outcome
checks_outcome
error
operation_id
result_ref
```

在 detail/result 内新增独立的执行后观察记录与汇总。必须能区分：

```text
脚本完成
检查失败
观察部分失败
结果转换失败
```

不要压成一个容易误解的 `success=true`。

新增摘要应保留错误原因、失败阶段、目标身份和至少必要的实际记录。不能再次退化成只有“读取 detail”的提示。原始有界 detail 仍保存在同一 receipt 下，不迁移 ledger schema。

### Description

明确告知模型：

> 新建输出用 observe_after；已知修改可在一次语义批次内完成并回读。Partial 后先看原操作留下的事实，再进行针对性修正。执行成功不等于 checks 或 visual 验证成功。

保留 stdout/stderr 丢弃、`result` 回传、等待不等于超时、no-blind-replay 的说明。

---

## B. `hia_capture` Contract

### Input

保留现有：

```text
frame
resolution
purpose
bounds
```

新增：

```text
target:
  {"paths": [绝对节点路径]}     1–8 个
  或
  {"selection": true}          当前节点选择，不是组件选择

view:
  "current" | "front" | "right" | "top" | "three_quarter"
  默认 "current"
```

示例：

```json
{
  "purpose": "review",
  "target": {
    "paths": ["/obj/shading_asset/OUT"]
  },
  "view": "right",
  "frame": 72,
  "resolution": [1280, 960]
}
```

**关系约束：**

* `target` 与旧 `bounds` 互斥。
* `target` 和非 current 的 view 只用于 review。
* 非 current 的 view 必须有 target 或显式 bounds。
* 旧的无参数 diagnostic 行为保持不变。
* 一次调用仍然只生成一张图，不自动前后截图，不增加多图 batch。

选择在操作实际开始时解析，记录确切 resolved paths。不要把排队前的 selection 当作执行时 selection。

### Target 支持范围

支持 SOP 几何节点，以及能够明确解析到显示 SOP 的 OBJ 几何对象。

不接受任意 subnet 递归展开，不把 LOP/USD primitive path 当作 SOP 路径，不默认处理 DOP object、COP image 或组件选择。

明确记录：

```text
requested target
resolved node paths
实际 geometry source
local bounds / source space
用于 framing 的 bounds / destination space
取样 frame
viewpoint
```

**先建立请求 frame，再读取该帧的目标 geometry、transform 和 bounds。**不能用当前帧的 bounds 去拍另一个帧。

### 坐标与 framing

复用 TC-1 的空间事实，增加一小块显式转换逻辑；不要建设通用坐标系统平台。

对象变换需要包括父层变换。旋转或非均匀缩放下不能只转换 bbox 的 min/max 两点，应转换八个角，再形成用于 framing 的包围范围。

world space 与当前 viewer 的建模空间不能想当然视为相同。必须在真实 H22 的 OBJ 与 SOP viewer 情况中核对；无法确认转换时，返回明确不支持，而不是靠猜测拍图。

命名视角统一定义为世界轴语义，返回实际方向/投影事实。优先使用经过验证的 stashed camera 与 native framing。某类固定视口无法安全切换时，返回 `REVIEW_VIEW_UNSUPPORTED`，不要偷偷换 pane 或创建临时相机节点。

### 不改变 authoring 内容

`target` 是 **framing target，不是 isolation 指令**。

不得为了截图：

```text
改节点 display/render flags
改 selection
切换当前 network
隐藏其他用户资产
改材质
修改或创建相机节点
```

如果目标不是当前显示输出，应返回当前显示来源与警告；不能把“拍到了当前 viewport”包装成“已经看到了指定 SOP 的精确输出”。

本轮不通过像素启发式判断目标一定可见。

### Restore 与 error

继续保存并恢复 frame、view、camera binding/lock 及临时修改的显示状态；新增视角涉及的投影、方向、缩放等也必须恢复。

恢复失败与 capture 失败分开报告。有效图像可以随恢复失败的 receipt 返回，但整体必须明确需要注意，不能伪装成功。

空几何、缺失目标、不支持的空间或视口，应先返回明确原因，不生成具有误导性的空截图，也不回退成另一种 authoring 行为。

### Artifact / operation

继续使用现有 `ArtifactStore` 和原生 MCP image。图像尺寸、PNG 校验、内容哈希与 workspace 路径边界不变。

`hia_operation get` 读取原 capture 的图像与 receipt，不能重新截图。新增 metadata 不得超过现有 manifest 读取边界；不要为了多塞 context 扩大整个 artifact 协议。

---

## C. 其他 Tool 的变化边界

| Tool                 | 要求                                                  |
| -------------------- | --------------------------------------------------- |
| `hia_context`        | 不新增字段                                               |
| `hia_inspect`        | 复用 TC-1 view/serializer；可提取小型内部 collector，但不改已有输入语义 |
| `hia_lookup`         | 不扩搜索范围、help provider 或知识体系                          |
| `hia_operation`      | 保留 action；支持正常展示/查询新增结果，不增加执行或重放入口                  |
| `hia_project_memory` | 完全不扩展                                               |

特别注意：**普通 inspect 的容错 collector 不能取代 execute 的严格 before-observation。**

---

## D. Backend 工作项

按四块实施：

**执行后回读。**在 `scene.py` 中建立明确的 post-execution 路径，保证正常、partial、cancel、scene replacement 分支都有稳定结果；不是简单在最后加一个 list comprehension。

**失败现场诊断。**复用现有结构读取，明确可读与跳过项目；保留原异常及 mutation outcome，不让诊断异常覆盖原始失败。

**目标化截图。**增加小型 target resolver、bounds 转换及命名视角适配；继续复用已有 capture/restore 和 artifact 实现。

**结果出口。**针对 execute/capture 扩充有用摘要，保留调用标识、实际记录与细节入口；不复制一套独立 receipt/result 系统。

不要使用临时节点来计算观测结果。不要引入新的 executor queue、数据库、长期 watcher 或全场景快照。

---

## E. Architecture Invariants

必须保留：

1. **单一主线程 HOM 执行权与现有有界队列。**
2. **操作 admission、ID、payload conflict、durable receipt 不变。**
3. **scene epoch 只表示场景代际，不假装检测所有人工编辑。**
4. **unknown / partial / running 不允许盲目重放。**
5. **检查、观察、序列化失败不能改写已发生的 mutation。**
6. **取消不等于回滚；checkpoint 不等于硬中断。**
7. **只恢复本次 capture 临时修改的状态，不清理用户场景。**

不要让“执行后反馈更方便”破坏这些已经存在的语义。当前 runtime 的状态提交与结果摘要是分离的，这个边界继续保持。

---

## F. Tests

只增加本次风险对应的测试：

| 风险              | 必须证明                                    |
| --------------- | --------------------------------------- |
| 新目标提前解析         | observe_after 中尚未存在的节点不会阻止脚本创建它         |
| 局部观察失败          | 一个新目标缺失，其他回读仍返回；completed mutation 不被改写 |
| 执行前保护退化         | 原 observe/preconditions 失败仍然阻止 mutation |
| Partial 诊断扩大副作用 | 失败后不自动 eval/cook；跳过项原因明确；原异常保留          |
| 取消/换场景          | 不在取消后继续昂贵观察，不把另一 HIP 当作旧目标              |
| 结果过大            | execute 首屏仍有实际事实；标识完整；detail 对应同一原操作    |
| 目标 framing      | 非默认父变换、旋转、非均匀缩放及多个目标的 bounds 正确         |
| 请求帧             | 使用请求帧的 bounds，不使用旧帧范围                   |
| Capture 恢复      | 成功、截图失败、恢复失败分别有正确状态；相机参数不被污染            |
| 不支持目标           | 空几何、非显示输出、错误空间、无 viewer 明确报告            |
| 原图重取            | 查询 receipt 不再次截图；artifact 完整性继续有效       |

保持原 receipt、epoch、lost-response/no-replay 和 capture fault tests 通过。

Schema、Adapter、Runtime 使用一致校验；不只测内部函数，至少包含真实 stdio/Adapter 到 queued operation 的 contract 路径。

---

## G. Real Houdini Acceptance

### 技术验证：必须执行，不依赖模型登录

使用隔离测试 HIP，通过生产 Runtime 路径验证：

**一次执行创建多节点网络，并在同一 receipt 中返回新输出的 node/parameter/geometry facts。**

另做一次受控部分失败：脚本创建部分节点后抛出明确异常。验证 partial receipt、有限现场诊断，以及随后一次针对性修改没有删除重建整个资产。

截图使用真实 Houdini GUI，不用 hython 代替。包含相机锁定、SOP/OBJ 上下文、非默认父变换、请求帧变化，以及截图/恢复故障路径。

允许通过专用测试驱动验证 backend；这属于技术验证，不能包装成自然语言模型验收。

### 自然语言任务：只做一组两轮，不新增大型 A/B 框架

另建一个小型百叶窗测试 HIP：已有窗洞、窗框、叶片模块、相机和无关资产，但没有目标百叶网络。至少一个父对象有非默认变换。

**第一轮：**

> 利用场景里已有的窗洞、窗框和叶片模块，制作一套可继续编辑的横向百叶。叶片数量、厚度和开合角度需要可调，整体放在现有窗洞内。保留其他场景内容，检查叶片间距和侧面连接，并给出能看清正面及侧面结构的图像。

模型自己决定节点和 workflow，不提供预期工具调用序列。

随后，测试者修改现有父对象变换，并把当前 viewport 移到无关位置；记录这次人工变化，不帮助模型修正网络。

**第二轮：**

> 我刚调整了这组窗户的位置和朝向。请继续修改原来的百叶，改为十二片，并让开合角度在第 24 到 72 帧从 15 度变到 65 度。保留我的场景调整，不要整套重建。检查结束姿态是否碰到窗框，补一张第 72 帧能看清侧面关系的图像。

检查模型是否重新理解现场、继续修改原网络，是否真正利用执行后回读与目标截图。采样帧正确不代表整个动画区间已验证，报告中不得扩大结论。

受控 failure test 与自然语言任务分开，不能为了展示“会恢复”偷偷向模型任务注入故障。

### Quality Evidence

复用现有 history、receipts 和计数方式，只新增必要分类：

```text
execute / inspect / lookup / capture 次数
observe_after 项目与成功/失败/跳过数量
为获取新建目标结果追加的 inspect 次数
仅用于准备视口的 execute 次数
API 猜测与重复调用
partial 后的修正方式
截图目标、帧、恢复事实
第二轮节点连续性和人工修改保留情况
```

**预期可审查收益：**新建目标无需额外 inspect 才获得标准结果；按节点截图无需先写视口准备脚本。是否减少了真实模型总调用数，要依据记录，不提前宣布百分比。

---

## H. Git

语义提交可按实际工作组织，例如：

```text
feat(execution): add bounded post-execution observations
feat(execution): report passive diagnostics after partial batches
feat(capture): frame explicit geometry targets in review views
fix(results): preserve actionable execution feedback
test(feedback): validate target capture and continued editing
```

TC-1 的标识摘要修正单独留在 #6。

不要使用无信息提交名，也不要把验收 fixture、模型历史、凭证或用户路径混进功能提交。公开证据保持最小脱敏；原始运行数据保留在本地 review 目录。

---

## I. Merge Gate

### TC-2 技术合并的硬条件

**以下全部满足才允许合并：**

* 新 contract 经真实 wire/runtime 路径验证，旧调用兼容。
* 新建目标在原执行 receipt 内获得有效回读。
* Partial 诊断不自动求值、cook、修复或重放。
* 真实 H22 GUI 已验证目标 framing、请求帧及状态恢复。
* 无相机参数、selection、节点 flags、人工编辑污染。
* 既有可靠性回归和当前候选 CI 通过。
* PR diff 只包含 TC-2，不重新提交 TC-1。
* 所有未完成的模型验收仍明确登记。

**不能仅凭 CI 合并新增 capture 状态操作。**这部分风险是具体的，真实 GUI 验证是必要门槛。

### 模型效果审批

完成一次两轮自然语言任务后，才能宣称 TC-2 已证明可改善真实 authoring。

若唯一阻塞仍是外部登录条件，而上述技术硬条件已经全部满足，**允许技术合并，但阶段状态必须保留为“模型效果待验证”**。`TC1-A1` 与 TC-2 的任务证据分别记录，不能互相顶替。

不要为了补一个任意百分比反复跑实验，也不要在没有模型证据时宣布“Codex 已明显更聪明”。

**通过本阶段门槛后即收口。Codex 现在可以启动 `codex/tool-capability-feedback`，并行完成 #6 的小型收口修正；无需等待 TC-1 的护栏对照才继续施工。**

[1]: https://www.sidefx.com/docs/houdini/hom/hou/GeometryViewport.html?utm_source=chatgpt.com "hou.GeometryViewport"
[2]: https://www.sidefx.com/docs/houdini/hom/hou/OpNode.html "hou.OpNode"
[3]: https://modelcontextprotocol.io/specification/2024-11-05/server/tools "Tools - Model Context Protocol"
