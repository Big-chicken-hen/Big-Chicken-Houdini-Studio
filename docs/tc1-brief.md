# TC-1: installed discovery and working-set observation

Approved user-supplied Pro review, 2026-09-08. Actual branch base:
`1e9f0f4dc43465bd221b3e0832a5e75d6cd1aa66` (merged PR #5).
Branch: `codex/tool-capability-discovery`. The operative execution brief below
is preserved from the supplied review. It supersedes the former next-stage
branch plan: Thread requirements and UI work remain outside TC-1.

# 4. Codex Execution Brief

## Role

```text
Pro = 审批、工具层方向、最终 review
Codex = implementation、tests、Houdini validation、commits、push、PR
```

本 Brief 已批准 TC-1 的实施方向。Pro 未修改仓库、未运行测试、未执行 Houdini 验证。

不要重新启动整体架构讨论。先实现下面这组能力，再用真实任务验证；只修本阶段发现的缺陷，不顺手加入下一阶段。

## Branch / PR

| 项目         | 要求                                                                                           |
| ---------- | -------------------------------------------------------------------------------------------- |
| Repository | `Big-chicken-hen/Big-Chicken-Houdini-Studio`                                                 |
| Branch     | `codex/tool-capability-discovery`                                                            |
| Base       | 最新 `main`；本次审查基线为 `1e9f0f4dc43465bd221b3e0832a5e75d6cd1aa66`                                 |
| 单一 PR 目标   | 提升当前安装发现与局部场景观察，降低错误猜测和机械往返                                                                  |
| 主要修改范围     | `mcp.py`、`scene.py`、`inspection.py`、`instructions.py`；必要的小型 lookup/help 模块；有界 result 摘要及对应测试 |
| 不在范围内      | Launcher/Panel、账户、模型切换、记忆扩展、Thread requirements、runtime/ledger 重写、额外领域工具                     |

开始前读取仓库 `AGENTS.md`，记录实际 base SHA。若 main 已前进，检查相关差异再继续，不恢复旧 PR 分支，不覆盖用户其他 worktree 或未提交工作。

---

## Tool Contracts

### A. `hia_context`

**Input：**继续接受 `{}`。

保留已有核心字段及保存状态语义，新增以下有限事实：

| 新信息                 | 内容                                                              |
| ------------------- | --------------------------------------------------------------- |
| `selection_summary` | `total`、`truncated`、最多 16 个节点的 path/type/category/parent 摘要     |
| `network_summary`   | 实际观察的 path、child category、可编辑性、可获取的 display/render 输出路径         |
| network 来源          | 标明来自哪个 pane 选择策略；fallback 必须明确，不声称一定是活动焦点                       |
| 时间上下文               | FPS、frame range、playback range、当前 Take 名称                       |
| 可用性                 | 无 UI、无 Network Editor、部分 HOM 方法不可用时，返回明确 unavailable/null，不伪造事实 |

不在 context 中访问 geometry，不求值全量参数，不枚举整张图，不扫描 packages。

现有 `network` fallback 字段可以为兼容保留，但必须让新的摘要明确它是 fallback，而不是已观察到的当前编辑网络。

**Description 要表达：**这是低成本工作入口；能获取对象身份与可创建的节点类别；它不是完整场景观察，scene epoch 也不是逐次编辑版本号。

---

### B. `hia_inspect`

保留现有 `views` batch 和六种 view，不另造查询语言。

#### `node` / `children`

扩展返回：

```text
path / name / full type / category / parent
已有 inputs
connections：source path、source output index、destination input index
flags：display、render、bypass、template，按节点能力返回
editability：网络内容是否可编辑、是否处于锁定资产边界
errors / warnings：有界文本
可安全读取的 cook facts
```

不支持的字段返回 null 或 unavailable，不把“不支持”转换成 false。

`children` 增加 `offset`，保留 limit 上限；按稳定规则排序，返回 `total`、`next_offset`、`truncated`。**只看当前一层，不默认递归。**

Cook facts 必须区分“是否需要 cook”“已有诊断信息”与“本次已验证 cook”。读取 graph 不得偷偷对所有节点 `cook(force=True)`。

#### `parameters`

保留 `pattern`、`offset`、`limit`，增加：

```json
{
  "view": "parameters",
  "path": "/obj/example/controls",
  "pattern": "*spacing*",
  "limit": 8,
  "include_values": true
}
```

`include_values` 默认 **false**。设为 true 时，只求值当前返回页的参数。

参数记录需要包含：

| 类型   | 内容                                                                   |
| ---- | -------------------------------------------------------------------- |
| 身份   | runtime name、template name、tuple name/组件关系、multiparm indices         |
| 设置依据 | data type、components、default、适用时的静态 range、menu tokens/labels、简短 help |
| 可选值  | 当前值，以及 `value_status` / 单项求值错误                                       |
| 边界说明 | 模板占位名不是可直接设置的实际参数名；动态菜单未求值                                           |

禁止为了发现参数而创建节点、展开 multiparm、执行按钮、运行 menu generator 或 callback。**读取值可能触发参数表达式及相关求值，description 必须说明，而不是将其承诺成绝对无副作用读取。**

`parms` 继续作为已知参数名的低成本读值入口，不删除。

#### `geometry`

保留已有 counts、四类属性、有限样本与数组/字典保护。

新增：

* bounds 的明确坐标空间与对应节点/空间路径；
* 可选 group 名称与 owner，限制返回数量，不展开全体 group 成员；
* 有界的可用性/错误说明。

本阶段不自动把所有 geometry 统一转换成 world space，也不宣称 bounds 可直接用于任意 viewport。不能确定空间映射时，明确告知调用方需要转换。

现有材质属性可通过 targeted attribute inspection 读取；不要把少量样本包装成完整材质分配报告。

#### 批量错误行为

**格式非法：**整次请求在执行任何查询前拒绝。

**合法请求中的局部目标失败：**保留其他 view 的成功结果，每项带 index、path、status 和结构化 error。顶层报告 `ok` 或 `partial`。

**关键兼容要求：**只改变普通 inspect batch 的聚合行为。`execute` 使用的 pre-observation 仍必须保持严格失败边界，不能因为复用“容错 inspect”而在前置观察失败后继续 mutation。

---

### C. `hia_lookup`

保留工具名与三类 source。新增 canonical metadata batch：

```json
{
  "source": "metadata",
  "requests": [
    {
      "kind": "search",
      "category": "Sop",
      "query": "orient curve",
      "limit": 8
    },
    {
      "kind": "search",
      "category": "Sop",
      "query": "copy instance",
      "limit": 8
    }
  ]
}
```

`requests` 限制为 **1–4 项**。本轮只批量化 metadata，不把不同 service 的查询混成通用 orchestration。

#### Metadata request 类型

| `kind`       | 必填                      | 可选及行为                                              |
| ------------ | ----------------------- | -------------------------------------------------- |
| `categories` | kind                    | 返回实际安装的 category 名称及标签，不硬编码 H22 类别表                |
| `search`     | kind、category、query     | offset、limit；明确的 include_hidden/include_deprecated |
| `type`       | kind、category、type_name | 参数模板过滤/分页选项；help 摘要或有界扩展选项                         |

Search 默认页大小 12，上限 32。新 canonical search 默认不包含 hidden/deprecated，但必须返回过滤规则与匹配中被过滤的数量。精确 `type` 查询永远允许查看已安装的隐藏或弃用类型，不能阻碍旧工程维护。

Lookup 不新增 scene path selector。模型已经可以从 context/inspect 取得 category 与精确类型；保持 metadata 查询只依赖安装，避免不必要地改变现有 epoch 边界。

#### Search 实现要求

不能继续把整段 query 只做一次完整子串匹配。

使用有界关键词匹配，覆盖：

```text
准确类型名
TAB label
已注册 alias
```

优先完整名称/别名匹配，再按命中词数量等确定性规则排序；提供 `matched_on`。不需要 embedding，不需要自维护同义词大全。

说明查询适合简短 Houdini 工作流关键词；**不宣称它能理解任意自然语言或已经搜索完整 help 正文。**

每个候选返回：

```text
category
精确完整 type name
label
bounded aliases
hidden / deprecated：true、false 或 unknown
简短 deprecation/replacement 信息（存在时）
匹配依据
```

查询级别返回实际 Houdini 版本、过滤信息、total、offset、next_offset、truncated。未知 category 应是可理解的错误，不能像现在一样悄悄变成另一种成功结果。

#### 精确 Type 说明

精确类型查询返回：

```text
完整类型身份与 name components
输入/输出数量约束
child category
可获取的类型来源：builtin/HDA 等
hidden/deprecated 原始事实
有来源的 deprecation reason/replacement
有界 help
按需参数模板页
```

`deprecated=false` 不等于 recommended。命名空间优先级不等于工作流建议。缺失 metadata 返回 unknown，不用猜测补齐。

参数模板 serializer 尽量与 instance inspection 共享，但显式标记：

```text
template_pattern ≠ runtime_instance
```

不通过临时创建节点来发现参数。

#### Help provider

必须做到**返回实际可读内容**，不能只加 `help_url` 字段就算完成。

执行顺序：

1. 读取指定类型可用的 embedded help。
2. 无 embedded help 时，解析并读取当前安装的对应节点帮助。
3. 返回明确 provenance、installation version、内容是否截断，以及可用的后续读取位置。
4. 当前安装未提供帮助时，返回 `available:false` 与原因；精确类型 metadata 仍可成功。

内置帮助需要覆盖实际 H22 验收环境使用的普通节点，不能只测试自制 HDA 的 embedded help。

实现为小型目标化读取器：利用当前安装的 help 定位方式；需要读取本地 ZIP 时，只读取目标 member、限制解压字节，不展开整个 archive。不要启动新的 help service，不自动导入全套文档，不构建 FTS/vector 索引。

HOM 能读取普通文件、opdef/oplib 及 HTTP，但 **本阶段禁止把 help lookup 变成任意 URL 抓取或主线程网络下载入口**。([SideFX][4])

Help 文本是文档数据，不是执行指令；不运行其中示例、脚本或外部命令。若帮助声明的版本未知或与安装不一致，明确标注，不能伪造“已验证为当前版本”。

#### HOM / documents

HOM 保留现有 signature 和 public-member discovery，补齐：

* `symbol="hou"` 的根模块发现；
* 更清晰的缺失 symbol / 无 signature 结果；
* 明确截断说明；
* schema 对 symbol、members、offset/limit 的一致约束。

仍禁止执行 descriptor、动态 getter 或任意待查询函数。

`documents` 保留现有显式导入文档查询。Description 必须说明它不是 installed help；`version` 作为文档过滤条件，不得让模型误以为能切换当前安装版本。

#### Compatibility

旧的单项 flat metadata 输入经一个薄 normalization 层继续使用同一后端。保留旧工具名与主要结果键；允许修正旧的无声截断和缺失分页，不维护两套 lookup 实现。

`tools/list` 的 schema、stdio 入口、Adapter 与 Runtime 校验必须一致。使用 tagged `oneOf` 时，修正当前只检查顶层 properties/required 的入口逻辑，测试真实 wire path；不要建立完整通用 JSON Schema 框架。

---

### D. 结果大小与 Error Contract

针对本次三类 observation 结果，建立一个小型共享预算/摘要方法。

**普通首屏结果以约 12 KiB 为设计预算，避免撞上现有 16,000 字节的整块替换门槛。**这是结果设计预算，不是要求把 request limit 或 ledger detail limit 改成同一个值。

超限时保留：

```text
请求身份与目标
状态及错误
核心标量事实
部分实际记录
total / truncation 信息
正确的分页或完整 detail 获取方式
```

不能只剩一句“去读 operation detail”。不能无声丢弃查询项、伪造空集合，或给出会跳过尚未返回记录的 `next_offset`。

保留原始有界 detail 和原 receipt；不更改执行事实。截断前继续执行现有 redaction。

Error 至少有稳定 code、message、request/view index 和目标。**unknown、unavailable、empty、unsupported 是不同情况。**

本轮维持已有 MCP wire version 和 JSON TextContent；为新 JSON payload 编写结果 schema/fixture 与说明，不顺手做协议升级。

---

### E. 其余四个工具

| Tool                 | 本轮动作                                                          |
| -------------------- | ------------------------------------------------------------- |
| `hia_execute_hom`    | 保留输入与执行语义；明确 stdout/stderr 丢弃、result 通道、等待与超时区别、partial 后必须观察 |
| `hia_capture`        | 不加 mode；澄清 bounds 空间和视觉证据边界；复用现有恢复机制                          |
| `hia_operation`      | 保留 get/detail/cancel/list；说明何时需要查询原操作；不增加重放入口                 |
| `hia_project_memory` | 不扩功能，不自动注入，不实现 Thread requirements                            |

---

## Backend

按以下工作单元实施，不只修改 schema 文案：

**工作单元一：共享观察记录。**
实现紧凑的 node/network record 和 parameter metadata serializer，供 context、inspect、type lookup 按不同深度调用；不要让 context 顺带执行昂贵 inspection。

**工作单元二：安装目录查询。**
实现 category 枚举、名称/标签/alias 关键词匹配、确定性分页和类型状态读取。Catalog 不需要持久化数据库；避免长期缓存导致安装或卸载 HDA 后继续返回旧能力。

**工作单元三：目标化帮助读取。**
实现一小块 installed-help adapter，验证普通内置节点与 embedded HDA 两条路径。具体本地 resolver/API 必须在实际 H22 安装中核对，不按训练记忆猜函数名。

**工作单元四：批量结果与预算。**
实现 per-item result 聚合和保留决策信息的摘要；保持 mutation/check/receipt 状态与观察结果状态分离。

---

## Existing Architecture：必须保留的可靠性语义

1. 所有 live HOM 场景访问继续通过已有主线程执行边界；现有静态 HOM symbol discovery 的安全路径保留。
2. receipt admission 先持久化，operation identity 和 payload conflict 处理不变。
3. scene replacement 后旧 epoch 不得继续写入；**epoch 不代表普通参数和连接从未被人工修改**。
4. 不确定提交、运行中操作、partial mutation 不能盲目重放。
5. queued cancellation 与 running cooperative cancellation 的区别不变；不承诺硬中断 blocked HOM。
6. Undo group 不升级为事务承诺；checks、observation、result conversion 失败不能改写已完成 mutation 的事实。
7. capture 的 frame/view/camera 恢复与独立错误报告必须保持。

上述机制已在当前代码中存在，本轮是保留它们，不是重新实施。

---

## Description / Prompt Changes

修改现有 `SCENE_INSTRUCTIONS`，不追加一份长篇工作流百科。补充四条原则：

**新建与维护分开。**新网络选择工作流时，必要时查当前安装和帮助；维护已有旧节点不等于必须迁移，不因 deprecated 就擅自替换用户网络。

**未知设置先查证。**对不确定的节点、参数 token、typed API 或 enum，使用对应 lookup/inspection；已知、确定的小改动直接执行并窄范围 readback。

**按工作对象合并观察。**一起读取相关 network、目标参数及必要 geometry，避免没有新问题却反复获取相同 context。

**执行以可审查的语义步骤为单位。**不把每个参数写入拆成 tool call，也不把建模、渲染、导出和所有后续修改塞进一个巨型脚本。

给工具放少量示例，至少覆盖“未知节点关键词发现”“两个类型比较”“参数 metadata 与当前值同读”。验收 prompt 不包含这些调用指令。

---

## Old HIA / New Sources

优先查看：

```text
旧 HIA / executor.py
  _search_node_types
  _node_help / _node_help_result
  _parameter_templates
  局部 graph、geometry 和 missing-target 处理

旧 HIA / knowledge_index.py
  安装帮助文件、archive 与来源标识的处理
```

只提取小算法和失败经验。不要导入旧 executor 或 knowledge store；旧代码中“读取失败就回退 false”的模式，也不能用于判断当前类型是否弃用。

外部资料限定在实际需要的官方 HOM、H22 installed help 与相关 MCP/Codex contract。**已有证据足够实施，不要求再做社区方案横向大调研。**

---

## Tests

只增加与这次变化直接相关的测试：

| 风险            | 必须覆盖                                                                       |
| ------------- | -------------------------------------------------------------------------- |
| schema 与后端不一致 | canonical/legacy 输入；缺少必填项；混用分支字段；bool 冒充 int；stdio tools/list → tools/call |
| 当前安装发现错误      | 不知道精确名时按 label/alias 找到；稳定分页；hidden/deprecated/unknown；精确查询仍能读 legacy      |
| 伪造兼容性         | 无 lifecycle API 不得返回 false；replacement 不存在或 metadata 不完整要明确表示              |
| 偷偷求值或创建       | 默认参数发现不 eval、不创建节点、不执行动态菜单或 callback                                       |
| 局部失败          | 一个 view/type 不存在，其他结果仍返回；但 execute 前置观察失败仍阻止 mutation                      |
| 截断            | 大于默认页与预算；首屏保留事实；cursor 不跳项；redaction 先于截断                                  |
| 几何读取膨胀        | 不展开全部元素或 group 成员；bounds 空间明确                                              |
| Help 读取       | builtin、HDA、缺失、错误定位、大文件、archive 限额；不触发网络或全库建索引                             |
| 既有可靠性回归       | 原 receipt、epoch、lost-response/no-replay、capture restore 相关测试继续通过           |

保留已有 signature/descriptor 测试，不把它们重新包装成此次新增成果。

---

## Real Houdini Acceptance

### 测试场景准备

由实施侧创建一个专用、可重置的 HIP fixture，不使用用户生产 HIP。

场景包含：起伏且弯曲的步道/坡面、引导曲线、两种已有立柱模块、少量现有材质、一个相机和无关保留资产。至少一个输入有非默认对象变换；模块控制包含实际参数或 multiparm，以验证 instance metadata。

**不要预先搭好目标护栏网络。**

任务模型只看到普通 Studio 环境与下面自然语言任务，不看本施工 Brief、不看预期节点清单。

### 第一轮任务

> 请利用场景里已有的曲线、坡面和两种立柱模块，沿步道外侧做一套可继续编辑的护栏。立柱间距大约 1.2 米，随路径转向并正确落在坡面上，扶手沿弯道连续。两种模块有稳定、可调的分布变化，并能调整整体高度和间距。保留已有步道、材质、相机及其他资产。完成后检查转弯处和坡度变化处，给出能看清整体与局部连接的视觉结果。

不指定节点，不禁止某个节点名称，不要求为了计数必须 lookup。

### 第二轮任务

在同一 native Thread、同一 HIP 中，先由测试者移动一段引导曲线，再发送：

> 我刚调整了右侧这段曲线。请在现有护栏上继续修改：把立柱间距改为 0.8 米，整体加高 20%，并在我选中的位置附近留出约 2 米的通行开口。保留现有模块分布规则和其他场景内容，不要整套删除重建。再检查新开口和改动后的转弯连接。

这一轮必须验证它是否重新读取必要事实、尊重人工变化并修改原网络，而不是复用过时坐标或重跑第一轮生成脚本。

### 场景质量检查

检查实际结果，而不仅是节点存在：

* 立柱位置、方向、坡面接触与扶手连续性是否合理；
* 参数控制是否真实有效，网络是否可读、可编辑；
* 原有资产、材质、相机和人工曲线修改是否保留；
* 第二轮是否沿用原网络，开口是否真实出现；
* capture 是否提供可用图像且恢复原视图状态；
* 模型是否真的依据图像或检查结果作出判断，而不是只宣称“检查完成”。

不要求本任务顺便完成 HDA 发布、Karma 最终渲染或 simulation。

---

## Quality Evidence

使用相同 fixture、相同自然语言任务、相同 Houdini 安装、Codex executable、模型和 effort，对照：

```text
审查基线 main：独立新 Thread，连续两轮
TC-1 candidate：独立新 Thread，连续两轮
```

至少保留一组完整配对记录。若出现明显随机性或异常，只追加解释所需的配对，不挑选最漂亮的一次覆盖失败记录。

记录以下最小集合：

| 维度 | 记录                                                                        |
| -- | ------------------------------------------------------------------------- |
| 版本 | base/candidate SHA、Houdini build、Codex version、model/effort、fixture 标识    |
| 调用 | 各 MCP tool 次数；inspect view 数量；metadata request 数量                         |
| 错误 | API guess failures、无效参数/类型、错误 option、缺失目标及恢复方式                            |
| 浪费 | 无必要的重复 inspect/lookup、重试、capture、detail 读取                                |
| 延迟 | first useful authoring action latency；已有 receipt 的 queue/execution timing |
| 结果 | 两轮 HIP、关键网络/参数事实、视觉结果、保留内容与第二轮连续性                                         |

**backend 内部轮询不计成模型 tool call。**有效的零结果搜索不自动算 API guess failure。不能靠跳过视觉检查或把全部工作塞进一次不可审查 execute 来制造效率提升。

使用现有 native history、receipts 和一个小型提取脚本即可，不建立新 telemetry 系统。原始记录留在本地 review 目录；公开证据去除凭证、私人路径与无关内容。

---

## Git

使用语义明确的 commits，例如：

```text
feat(context): expose bounded Houdini working-set facts
feat(inspect): add paged graph and parameter observations
feat(lookup): add installed type discovery and targeted help
fix(mcp): preserve actionable bounded observation results
test(authoring): record two-turn capability acceptance
```

按实际改动组织，不为凑这些标题机械拆分；不使用 `fix`、`polish`、`final` 等无信息提交名。

Codex 完成实现、测试、真实验证、commit、push 和单一 PR。PR 必须区分源码测试、真实 Houdini 执行和模型端实际验收，不能相互替代。

---

## Merge Gate

**全部功能条件必须通过：**

1. 三个工具的 schema、真实行为、错误与分页一致。
2. 能在当前安装中发现未知精确名称的候选，读取实际参数设置依据和目标化 help。
3. 普通工作对象观察不再因局部缺失目标丢失其他结果；常规结果不被无内容的 detail 提示取代。
4. 自然语言验收两轮完成，网络可编辑，人工修改与无关内容保留。
5. 没有 no-blind-replay、scene epoch、partial-result 或 capture restore 回归。
6. 没有 hardcoded Copy Stamp 黑名单、针对验收的工作流答案或隐蔽的专用建模工具。

**效率/质量条件至少满足下列一种，并提交完整对照：**

* 在同等合格结果下，观察/发现类外部调用减少 **至少 20%**；
* 基线存在 API 猜测失败，candidate 降至零，且总 tool-call 数不增加；
* 基线无法完成该连续编辑任务，而 candidate 两轮完成，且逐项审查未发现可明显消除的机械往返。

这里的百分比是**本阶段的验收门槛，不是已经测得的收益**。延迟不设凭空的绝对秒数门槛，但由新增 metadata 扫描或 help 读取造成的明显主线程阻塞必须修复。

**若只增加了 metadata 字段，却没有上述任何行为或质量收益，不批准 merge。**

通过后，提交 Pro review；获批即结束 TC-1 并 merge。**不要在收尾时再加入 Thread requirements、材质工具、simulation 工具或下一轮架构抽象。**

[1]: https://www.sidefx.com/docs/houdini/hom/hou/OpNodeType.html "https://www.sidefx.com/docs/houdini/hom/hou/OpNodeType.html"
[2]: https://modelcontextprotocol.io/specification/2025-11-25/server/tools "https://modelcontextprotocol.io/specification/2025-11-25/server/tools"
[3]: https://openai.com/index/unlocking-the-codex-harness/ "https://openai.com/index/unlocking-the-codex-harness/"
[4]: https://www.sidefx.com/docs/houdini/hom/hou/readFile.html "https://www.sidefx.com/docs/houdini/hom/hou/readFile.html"


