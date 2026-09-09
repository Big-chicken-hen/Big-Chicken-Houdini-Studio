# 审批结论

**下一阶段停止扩展大块 Tool Capability，转入 Release Readiness。第一项工作是修复 PANEL-1，而不是继续加工具，也不是先做视觉美化。**这与附件中提出的性能、产品成熟度、真实 Panel bug 和对外发行四项目标一致。

本次核对后的仓库状态是：

| 项目        | 当前状态                                                           |
| --------- | -------------------------------------------------------------- |
| `main`    | `6c88102693fc4c12131d6a7236ba6b351114dce4`，已包含 PR #8、#9        |
| PR #10    | 仍然开放，非 Draft；head 为 `e9582f3a865bdcced83c9e4902b731c1094bb9fa` |
| PR #10 CI | 当前 head 的 workflow 成功                                          |
| 模型验收      | TC1、TC2、TC3 都已经实际运行，**不能再写成等待登录**                              |
| PANEL-1   | 仍未复现、未定位、未修复                                                   |

这些状态来自最新分支、PR 和验收记录，不沿用前几轮的状态摘要。

**审批决定：PR #10 可以按“技术集成”收口合并，但不宣布 TC-3 的完整模型效果或资产质量通过。PANEL-1 不必阻塞这次技术合并，却必须阻塞公开发行。**

同时说明本次证据边界：我读到了源码、版本化验收报告和具体失败操作记录；完整 native thread exports、逐项参数及 PNG 原件仍位于本地 `.runtime/reviews/`，没有出现在可读仓库内容里。我定位到了当前 CI 的 `native-ui-review` 图片工件，但下载接口拒绝了该二进制端点，因此**没有对最新截图作像素级通过判断，也没有把报告中的“已看图”说成我亲自看过**。下面会明确区分源码已确认的问题与需要 Codex 用原始记录验证的因果判断。仓库没有被我修改。

---

# 1. 性能 / 模型能力审查

## 1.1 已经确认：TC-1 的效率门槛没有通过，但原因不是一句“工具变慢了”

验收记录中的实际分布如下：

| 两轮合计    | TC1 基线 | TC1 候选 |      变化 |
| ------- | -----: | -----: | ------: |
| Context |      2 |      2 |       0 |
| Inspect |      0 |      2 |      +2 |
| Lookup  |      0 |     17 |     +17 |
| Execute |     26 |     27 |      +1 |
| Capture |     14 |     13 |      −1 |
| **总调用** | **42** | **61** | **+19** |

但基线的 26 次 execute 中，有 **12 次是只读观察或发现脚本**。因此，“基线 lookup 为零”不等于“基线不查询”；候选额外的 17 次 lookup 也不能全部直接归为浪费。真正需要比较的是**查询解决了什么问题，是否重复取得已有事实，以及获得事实后有没有减少错误或后续探测**。

当前报告还提供了一个很重要的时间分解：首次成功 authoring 到达 Runtime，基线约 119 秒，候选约 141 秒；而这次操作本身的 queue/execution 分别约为 `0.062/0.076` 秒和 `0.063/0.143` 秒。

**这能证明候选更晚开始有效修改，不能证明这 22 秒主要由 Runtime metadata 开销造成。**模型推理、网络、更多前置查询与具体工具耗时，尚未被完整拆开。

### 对其他两项验收的判断

**TC2：没有使用 `observe_after`，不自动构成失败。**模型在八次 execute 中自行编写了 HOM readback；任务和连续编辑检查通过，四次 capture 也成功恢复。只要自写 readback 已经提供足够事实，就不应该为了“新功能采用率”再要求一次标准观察。已证明的是 target capture 的价值，不是整个反馈 contract 都被采用。

**TC3：staged execution 确实被采用，但它不是调用数量的自动优化器。**55 次 MCP 调用中包含三次 staged 请求、六个步骤；出现参数封装和 HDA 类型迁移失败后，已完成步骤记录被保留，模型进行了新的局部修正。这是有效的流程能力证据。与此同时，弯道模块重叠、类型迁移后的节点身份变化，以及部分 `hou.session` bookkeeping 仍需要分别评价，不能用“步骤执行可靠”替代“作品已经正确”。

**决定：保留 TC-1/2/3，不回滚能力，不继续追加机械使用规则；下一步修工具的人机交互成本和结果组织。**

---

## 1.2 根因判断：目前可以确认到哪一层

| 问题              | 当前判断                                 | 工程动作                               |
| --------------- | ------------------------------------ | ---------------------------------- |
| Schema 拒绝造成纠正调用 | 报告明确记录了超出 `limit` 上限等错误              | 返回具体字段、允许范围和可修正信息，消除同类入口的无意义差异     |
| 过多 discovery    | 调用明显增加，但缺少原始逐项记录，尚不能全部定性             | 审核八个真实 turns，区分首次发现、必要刷新、重复读取和失败恢复 |
| 过多 capture      | TC1 两组都有十余次截图，值得重点审查                 | 对照每次前后的几何、视图和模型下一步判断，不能只按张数删除      |
| 自写 readback     | 本身不是浪费，也不必被 `observe_after` 替换       | 允许两条路径，禁止重复验证同一个已取得的事实             |
| 指令负担            | 当前 instructions 对批次、检查、未知结果、局部修正反复说明 | 合并重复规则，把内部协议解释移出常驻模型指令             |
| Runtime 回归      | 没有足够同条件数据证明普遍退化                      | 测量少量代表性请求的内部开销，再优化热点               |
| UI 卡顿           | 源码确认流式更新会重复处理整段 Markdown             | 将数据接收与绘制合并分开，避免每个 delta 都重排全文      |

当前 `SCENE_INSTRUCTIONS` 已经叠加多轮要求：既要求语义批次，又反复说明 staged 边界、检查、部分失败、未知结果和局部修正。内容并非都错，**问题在于重复和“每次都应做得更保险”的累积倾向**。

### 我不批准的解决方法

不设“每轮必须少于 N 次调用”。不强制每步检查、每轮 context、每次执行后截图，也不强制 staged 或 `observe_after`。

不新增节点白名单、Python 子集、通用风险分类器或“先问另一个模型”的审核层。**这轮不是进一步收紧合法 authoring 空间。**

---

## 1.3 批准的模型侧改动

### 精简常驻 instructions，保留六项真正影响决策的原则

常驻指令应只清楚表达：

1. 建立必要的当前场景上下文；现场变化后读取相关目标，而不是无条件重读一切。
2. 已知、确定的操作直接执行；只为尚未解决的不确定性查询。
3. 相关读取可以合并；已经取得且仍有效的事实不要重复验证。
4. 单脚本和 staged 都可使用；需要视觉判断或重新选择方案时再结束当前批次。
5. 未知或部分执行结果不盲目重放；依据原结果和当前现场局部修正。
6. 保留用户工作；破坏性操作和文件覆盖遵循具体授权，报告真实交付和验证范围。

`output_path()` 参数说明、步骤 JSON 上限、等待窗口、detail 获取方式等，放到对应工具描述和开发文档，**不在 developer instructions 与每个 description 中重复讲三遍**。

这不是删除可靠性要求，而是减少模型需要反复解读的内部实现细节。

### 明确允许有效的替代方式

**脚本内 readback 与 `observe_after` 二选一或按任务组合，不要求重复。**

**小型已知修改可以只有窄范围 readback，不强制同时声明 precondition、check、before/after observation 和 capture。**

**模型自行使用某种原生 HOM 组织方法，不因为没有采用插件新增模式就判不合格。**TC3 的 `hou.session` 应检查是否导致交付依赖隐藏状态，而不是立即增加一条全局禁止规则；验收已经证明外部 HDA 能脱离原会话工作。

---

## 1.4 批准的工具与 Runtime 改动

### Lookup：让一次查询更经济，不再建知识系统

当前搜索会先为整个 category 构造 label、alias、lifecycle 信息，再匹配查询；精确 type 查询默认同时读取参数与 help。已有一次调用内的 catalog 复用，不应重复建设同样的缓存。

批准以下有限优化：

**先匹配便宜字段，再为匹配项补较贵 metadata。**保持 hidden/deprecated 过滤和排序语义；不要为了减少耗时返回错误状态。

**复用同一次请求中的 help archive 和静态读取。**优先做请求内复用，不先做跨会话持久缓存；HDA 安装、卸载、更新后不能因缓存继续返回旧事实。

**利用已有过滤字段。**只需要帮助时，不附带无关参数页；只需要参数时，不附带整段帮助。description 给出一条明确选择原则即可，不新增一套 query language。

**修正 schema 错误反馈。**错误必须指出具体 request index、字段与上限，不能只返回“未匹配某个 oneOf”。同一种 metadata search 的新旧入口采用一致的页大小语义；保留兼容请求，不用扩大所有工具上限来掩盖问题。

### Result：优先限制生产量，而不是生成巨大对象后多轮复制压缩

继续保留完整调用标识、错误、实际记录与准确 cursor。

重点检查多次序列化、deep copy 和“同一摘要同时出现在多个层级”的成本。优化应先从**有界构造、单次序列化复用和非权威重复展示字段**入手，不牺牲原始 receipt/detail。

### Ledger：不得以降低持久性换取好看的耗时

Staged 当前确实会在步骤开始、结果确认和终态等边界持久化，并反复构造摘要。这些是需要测量的成本，不是可以凭感觉删除的成本。

保留 durable admission、step gate、no-blind-replay。**不关闭同步写入、不把步骤结果延后到整个流程结束才落盘，也不让下一步抢在前一步确认之前执行。**

报告中的约 22.22 秒 save/embed callback 是另一类问题：它涉及真实原生操作，不应一概归咎于 SQLite。

---

## 1.5 性能回归检查方式

只做一份小型诊断表，不建 telemetry platform：

| 层     | 测量内容                                          |
| ----- | --------------------------------------------- |
| 模型与网络 | turn 提交到首个有效 authoring；工具间空档；审批等待单列           |
| 工具链路  | Adapter 往返、queue、HOM/metadata、结果编码、receipt 提交 |
| UI    | 事件到达后到可见更新、Markdown 重排次数、历史加载量                |
| 用户结果  | 是否完成、是否可继续编辑、是否保留必要视觉验证                       |

历史实验用于定位问题；Runtime 优化用**同一安装、同一代表性请求集**比较修正前后。冷启动与预热读取分开。

门槛不是僵硬的总调用配额，而是：**没有未经解释的可重复 Runtime 回归；已识别的机械重复不再发生；质量与合法能力没有下降。**

---

# 2. PANEL-1 + Panel / Launcher UX 决策

## 2.1 PANEL-1：按发布阻断级 correctness 问题处理

现有 issue 记录只证明用户观察到“旧消息混入”和“消息被夹断”。它尚未证明混入发生在 native history、发送路径还是 UI，也没有确认实际发生问题的进程版本。

**现在不宣布根因，但已经有足够依据确定修复范围。**

### 优先核查的三个边界

**第一：消息身份与归属。**

`Transcript` 当前主要按 `item_id` 保存 card、completed 和 suppressed 状态；delta 分支也没有把 turn 归属传递给 `put()`。外围 Panel 已有 Thread 过滤和 callback guards，因此不能说系统“完全没有隔离”；但 reducer 自身仍应使用完整身份，而不是依赖每条调用路径都正确防守。

**第二：非原子 history snapshot 与 live delta 的合并。**

当前 hydrate 会把读到的 item 放入 `suppressed_deltas`，后续 delta 被忽略，并通过额外历史读取或最终 item 修复。这能避免一部分重复拼接，但也可能形成“内容暂停、回填、重新排列”的可见行为。必须用真实事件顺序判断它是否对应 PANEL-1，不能凭源码就断言。

**第三：内容完整性与显示高度。**

当前每次文本变化都重新 `setMarkdown()`，消息高度最多 1600，达到上限后启用内部滚动条。这是**显示层可能让人误以为截断**的路径，不等于文本真的丢失。Qt 的 `setMarkdown()` 会替换整个文档内容，因此频繁全量更新也值得单独处理。 ([Qt文档][1])

### 修复方向

批准建立一个**小型、仅内存中的消息投影 reducer**，不是第二份聊天数据库。

身份采用：

```text
connection_generation + thread_id + turn_id + item_id
```

Native history 仍是持久来源；live events 是当前更新来源。必须明确 start、delta、terminal item、历史摘要、完整历史项之间的覆盖规则。

尤其禁止：

* 根据相同文本去重；用户和模型都可能合法重复同一句话。
* 根据“哪个文本更长”决定哪个是真的。
* 不检查来源就把 snapshot 与 buffered delta 拼在一起。
* 让旧连接、旧 Thread 或旧请求的回调更新当前回复。
* 让历史摘要覆盖已经收到的完整 terminal 内容。

OpenAI 的原生生命周期本来就区分 `item/started`、delta 与携带终态内容的 `item/completed`；Studio 应正确投影它，而不是重新发明消息完成语义。([OpenAI][2])

---

## 2.2 History 恢复：按目标读取，不因每段 delta 重载整个对话

固定的 Codex 0.153.4 已有 `thread/turns/list` 与 `thread/items/list` schema，支持 cursor、Turn 过滤和不同 itemsView。

**批准优先利用它们，但必须验证实际 thread store 是否支持。**官方说明这些接口属于 experimental，部分 store 可以返回 unsupported；不能“schema 存在就当运行时一定可用”。([OpenAI Developers][3])

具体策略：

| 场景                            | 行为                                    |
| ----------------------------- | ------------------------------------- |
| 打开旧对话                         | 先读 metadata 与最近页面，较早历史按需加载            |
| 正常 streaming                  | 更新当前 item，不周期性回填全部 turns              |
| 丢事件 / 重连                      | 修复受影响 Turn 或 item，保留明确的 recovering 状态 |
| `item/completed`              | 用完整终态内容收口，不再追加迟到 delta                |
| 分页不受支持                        | 本连接记住能力结果，使用受控 fallback，不每次再试错        |
| `itemsView=summary/notLoaded` | 不当作完整正文，也不据此删除已显示内容                   |

正在恢复的 item，如果缺少可靠的 snapshot/delta 对齐信息，可以暂时显示最后一个可信快照并等待完整终态；**不能为了看起来连续而猜着拼接**。但这种限制只针对不确定的 item，不应让整个对话停止更新。

---

## 2.3 PANEL-1 验收

必须先取得一段最小失败链：

> native item / 历史内容 → Bridge 事件 → Panel reducer 内容 → 实际显示与复制内容。

分别判断是原生内容问题、投影问题还是渲染问题。至少覆盖：

* 同一 Thread 的连续两轮；
* A → B → A 切换，旧回调迟到；
* streaming 中重连，history 响应晚于 terminal item；
* 中文、长 Markdown、代码块与超过当前高度上限的消息；
* 重复事件、缺失 start、buffer overflow 与最终内容恢复；
* archive/delete 后旧事件不能复活消息；
* 正文完整但内层滚动导致的“假截断”。

**修完显示高度不能自动关闭“消息混入”；修完 Thread 隔离也不能自动关闭“正文丢失”。**必要时将 PANEL-1 分成两个可验收子问题，保留原报告。

---

## 2.4 Panel 视觉决策

保持现有 dark neutral、pink accent、原生 PySide6 与文本品牌，不重新设计产品体系。

当前主题已经给用户消息设置了不同 surface，并非完全没有区分；问题是层次还不够强。

### 消息层次

| 元素       | 本轮决定                                               |
| -------- | -------------------------------------------------- |
| 用户消息     | 较窄的右侧对齐块，宽度约 82%–88%；使用中性 elevated surface，保留“你”标签 |
| Codex 回复 | 左对齐、透明正文区，使用主要内容宽度；不做一串聊天气泡                        |
| 轮次之间     | 比同一回复内部更明显的间距                                      |
| 正文与元信息   | 正文保持现有可读字号；模型标签、时间、状态降为次级                          |
| 长正文      | 不无声裁切；统一可发现的完整阅读方式，复制仍取完整源文本                       |
| 图片       | 独立留在时间线上，带必要目标/帧说明；技术 JSON 不附在图片下面占位               |

不新增头像，不把整张用户卡染粉，不做微信式尖角气泡。

### Tool activity

**不重新创建一套工具日志系统。**现有 `tool_groups` 已经能折叠普通工具卡片，但它按整轮分组，而且只按“展开或包含图片”决定可见性，失败项没有独立可见规则。

升级为**连续 activity segment**：

> 在 Houdini 中工作
> 3 次查询 · 2 次执行 · 1 张视图

默认一行或两行。助手正常解释插在中间时，不能把前后的工具活动挪成一个破坏时间顺序的大组。

展开才显示每个请求与 receipt；**error、unknown、partial mutation、重要恢复警告始终可见**。图片不藏进技术详情。

“Edited 4 nodes”只有在实际结果支持时才显示。不能由四次工具调用推断改了四个节点。

### Working / progress

统一展示当前事实：

```text
Codex 正在处理
等待你的授权
Houdini 正在执行：生成铺装
阶段 2 / 4
正在获取视图
已请求停止，等待当前步骤结束
```

阶段计数来自 receipt，不是整个任务的完成百分比。Codex turn 结束但 Runtime 仍在运行时，必须保持“工作未结束”的状态。

---

## 2.5 Launcher：只做发行前的必要收口

保留既有 **Checking → Setup → Authentication → Home → Launching**。现有正式 UI specification 已经明确了正常 Home、未知启动、账号未确认与错误页面的语义，不应再推翻。

本轮只修五类问题：

**首次安装不出现开发命令。**普通用户不需要看到 venv、PYTHONPATH、workspace ID。

**错误有明确下一步。**区分缺失程序、版本不符、网络未确认、进程启动失败、Houdini 连接失败，不能统称“发生错误”。

**未知启动保留原请求。**不能因一次状态查询失败又提供一个会重复启动的主按钮。

**正常返回用户直接进入最近文件。**不增加必须观看的成功检查动画，不把缓存的账号状态当作当前认证。

**Diagnostics 可发现但不占首页。**默认错误只给发生了什么和该做什么，技术内容留在详情。

本次 UI 决策批准施工；最新 PNG 尚未在本会话成功读取，**视觉 merge gate 仍要求从实际安装包生成并检查原生截图与真实 Panel**。

---

# 3. Release / Distribution 方案

## 3.1 第一版定位和支持范围

先做 **`0.1.0-rc.1`**，通过下面的真实用户链路后发布首个公开预览版。不是长期挂着“原型”，也不在尚有 PANEL-1 时标成稳定发行。

首发目标收窄为：

| 项目                   | 首发决定                                                    |
| -------------------- | ------------------------------------------------------- |
| 平台                   | Windows 11 x64                                          |
| Houdini              | 22.0.368、带 PySide6 的 GUI 构建                             |
| Edition              | 首个正式验证目标为 Houdini FX；其他 edition 完成对应许可证与文件格式验证前不写入“已支持” |
| Codex                | **固定 0.153.4**，不是“最低版本及以上都支持”                           |
| 独立程序 Python          | 私有、固定补丁版本的 CPython 3.13 常规构建，随 RC 验证                    |
| 独立 Launcher Qt       | 保留 `PySide6-Essentials==6.8.3`                          |
| Houdini 内部 Python/Qt | 使用 Houdini 自带环境，不安装、不覆盖、不混入私有 Qt                        |

这是**目标支持矩阵**，不是声称新安装包已经验证过。Windows 10、其他 Houdini builds、Indie/Apprentice、Linux/macOS 在没有真实验证前明确列为未认证，不借 backend CI 扩大承诺。

当前代码本身声明 Python `>=3.10`、独立 UI 固定 Qt 6.8.3；这不等于已经完成多平台产品支持。

---

## 3.2 采用 per-user 安装器，不再以源码 setup 作为主入口

当前安装文档要求保留整个源码布局，并由已有 Python 建立 `.runtime/venv`。**这适合开发，不适合作为首发普通用户路径。**

### 发行方式决定

采用 **Inno Setup 的 per-user Windows 安装器**，正常安装不要求管理员权限。它已有非管理员安装模式，不需要 Studio 自建安装平台。([jrsoftware][4])

安装包包含：

* Studio 生产代码、Houdini package / Python Panel 资源；
* 私有 Python runtime；
* 固定的 PySide6 Essentials 及必要依赖；
* 固定、经过验证的原生 Codex 0.153.4；
* 已批准 SVG、所有必要许可证和版本清单；
* 开始菜单入口、卸载入口和最小启动故障反馈。

**不随包分发 Houdini，不随包分发账号或认证数据。**

Python 的 embeddable distribution 本来就用于被其他应用分发；这里采用独立目录布局，不做会在每次启动时重新解压、并改变 `sys.executable/-m` 语义的巨型单文件程序。([Python documentation][5])

依赖在构建时准备好，**首次启动不运行 pip、不编译、不要求 Node/Git，也不修改全局 PATH**。

### 路径边界

程序目录与现有用户 state/cache 分离。普通用户不必知道目录结构，但实现必须保证：

* 升级应用不会改变 native Thread 的 cwd；
* receipts、附件、Codex home 和场景关联不随程序版本搬家；
* Houdini 只加载 Studio 生产代码，不加载独立 Launcher 的 Qt；
* 外部已安装的 Python/Codex/Houdini 不被替换或卸载。

现有 child-process package 注入方式优先保留，不为了安装到其他用户机器就开始修改 `houdini.env`。官方 packages 本身支持这种独立配置方式。 ([SideFX][6])

---

## 3.3 First-run

普通用户路径应当是：

> 安装 → 开始菜单打开 Studio → 检测 Houdini 与随包 Codex → 官方登录 → 打开 HIP / 空场景 → Houdini 中出现 Panel → 输入任务。

缺少 Houdini 时，提供重新检测和选择已有安装；缺少兼容构建时说明要求，不显示一大段 Python traceback。

官方登录继续由 native Codex 返回地址并打开系统浏览器。**不增加 API key 设置，不复制用户其他 Codex 安装的认证文件。**

首次开启会话授权时给清楚说明；授权生效后验证普通工具调用能复用。PR #8 的测试支持其技术实现，但验证文档没有证明它解释了所有真实重复弹窗，RC 仍要检查实际流程。

---

## 3.4 Upgrade / uninstall

**首发不做自动 updater。**使用新的显式安装包升级，保留上一可用版本以便有控制地回退。

安装和升级不得强制结束用户 Houdini，更不能用进程名批量 kill。使用中的程序版本不被覆盖，提示用户正常关闭相关会话。

卸载默认移除程序、快捷方式和 Studio 自己安装的资源，**保留用户 state、native history、receipts、附件和输出文件**。

特别注意：当前未保存场景的默认输出位于 cache 下。**不能把整个 cache 视为可随便删除的垃圾。**清理功能先只清理明确的日志和可重建临时文件；临时创作输出必须单独说明并由用户明确选择。

许可证必须按实际随包组件审核，不是只复制一份 Qt LICENSE 就宣称完成。Qt 官方明确不同模块可能有不同条款，发行包应保持最小依赖并提供匹配的 notices、源码获取或其他所需履行材料。([Qt文档][7])

安装包附 SHA-256 与版本清单。有合法签名条件时签名；没有签名时如实说明，**不指导用户关闭 Defender 或其他系统保护来运行产品**。

---

## 3.5 Diagnostics / support

新增一个**用户主动触发的诊断导出**，默认只包含白名单字段：

| 包含                         | 不默认包含              |
| -------------------------- | ------------------ |
| Studio version、commit、包完整性 | 原始聊天正文             |
| Windows、Houdini、Codex 版本   | HOM script 和完整参数   |
| 连接状态、账号是否已确认               | token、登录 URL、认证数据库 |
| 最近失败 code、发生阶段             | 全量环境变量、代理凭证        |
| 有界耗时、工具/操作计数               | HIP/HDA、截图和用户目录扫描  |
| 经过脱敏的相关技术事件                | 整个 `.runtime` 打包   |

导出前显示包含内容和目标位置。更加详细的支持材料必须另外明确选择。

诊断导出不得自动上传，也不得因导出行为发模型请求或访问 scene geometry。

---

## 3.6 Release-candidate acceptance

**这次不再做算法 benchmark。**

在没有开发 checkout、没有配置 PYTHONPATH、没有预装 Studio Python 环境的 Windows 用户环境中：

> 安装真实 RC 包 → 启动 → 官方登录 → 打开已有测试 HIP → 自然语言修改 → 视觉反馈 → 第二轮修改 → 保存 → 关闭 → 再打开 → resume 原对话 → 第三次继续编辑。

一起验证：

**一次授权后的连续使用；消息不混、不丢；长回复完整；工具活动默认紧凑；Stop 状态诚实；已有文件与对话保留；升级/卸载不伤害用户数据。**

真实 RC 的 PANEL-1、授权和安装问题**不能再改成 deferred 后直接公开发行**。可以继续并行开发，但发布必须等这些产品条件通过。

---

# 4. 阶段 / PR 规划

采用四个短 PR，不做一个巨大“最终优化”PR。

| 顺序     | Branch                            | Goal / scope                                                     | Non-scope                    | Merge gate                                 |
| ------ | --------------------------------- | ---------------------------------------------------------------- | ---------------------------- | ------------------------------------------ |
| **R1** | `codex/panel-history-correctness` | PANEL-1 定位；消息归属、snapshot/delta 合并；相关绘制合并；原始 evidence 分类          | 不改主题方向、不调模型 prompt、不扩工具      | 旧代码可触发的回归测试、新代码通过；真实 Panel 内容与 native 内容一致 |
| **R2** | `codex/tool-use-efficiency`       | 八个 turns 的信息增益审查；精简 instructions；schema 错误；已测量的 lookup/result 热点 | 不加调用配额、不降低持久性、不建索引平台         | 机械重复有针对性减少；Runtime 无未解释回归；能力不缩水            |
| **R3** | `codex/release-ui-refinement`     | 消息层次、compact activity、progress、有限 Launcher 错误体验                  | 不重写 R1 reducer、不换 Qt/icon/品牌 | 原生 previews 与真实 Panel 通过；失败可见、长文完整、状态不误导   |
| **R4** | `codex/windows-release-package`   | 私有运行包、per-user installer、first-run、诊断、upgrade/uninstall、RC       | 不做自动 updater、不扩平台矩阵          | 实际安装包完成完整新用户链路，发布阻断问题清零                    |

R2 可以在 R1 修复期间先分析已存在的历史记录；R4 可以先做包清单和构建准备。**并行的是无冲突准备工作，不是让四个分支同时修改同一套 Panel 状态机。**

PR #10 技术合并后，以新的 main 为研发基线；历史实验候选、结果和不通过结论保持不变。

---

# 5. Codex Execution Brief

## Role

```text
Pro = 审批、产品与架构方向、review。
Codex = implementation、tests、Houdini validation、
        commit、push、PR。

Pro 本轮没有修改仓库，没有运行测试或 Houdini。
```

**现在进入 Release Readiness，不继续 TC-4，不扩渲染能力。第一阶段处理 PANEL-1。**

---

## A. Branch / base / scope

先按本次批准收口 PR #10 的技术集成。它不代表完整资产质量或模型效率通过，PR 说明继续保留验收缺口。

第一阶段：

```text
branch: codex/panel-history-correctness
base: 最新 main
reviewed PR #10 head: e9582f3a865bdcced83c9e4902b731c1094bb9fa
```

主要文件：

```text
src/studio/ui/conversation.py
src/studio/ui/panel.py
src/studio/bridge.py
必要的 native protocol contract / allowlist
相关 history / streaming / UI tests
docs/acceptance-issues.md
```

允许提取一个小型内存 reducer。禁止新建持久聊天数据库、重写整个 Bridge 或用清空消息列表隐藏错误。

更新 `AGENTS.md` 与当前阶段入口文档，明确旧 UI freeze 已被本轮的有限修正授权替代；不要改写历史验收结论。

---

## B. 先取得原始证据，再修改

读取 `docs/model-acceptance-results.md` 指定的原始 exports、receipts 和日志，不只读取 `metrics.json`。

四个 Thread：

| 记录            | Thread ID                              |
| ------------- | -------------------------------------- |
| TC1 baseline  | `01a0807a-8dfc-7f30-a8e8-1ecd24890ef1` |
| TC1 candidate | `01a08087-99d9-7323-886e-48a7b2a15ae4` |
| TC2 candidate | `01a08093-9169-79c0-a6fa-8d9eb89c8f08` |
| TC3 candidate | `01a0809b-2d19-7853-bd8c-cd260aadd352` |

完整路径与 workspace 映射使用现有报告，不复制认证目录，不把测试历史混进生产 workspace。

PANEL-1 的原进程版本尚未确认。先对照用户报告对应的 session；若原始事件不足，明确缺什么，并在专用测试对话里记录最小重现。不能直接宣称某个候选代码就是根因。

保存三层事实：

```text
native 原始 item / full history
Bridge 收到及投影的事件
Panel reducer 的完整文本与身份
```

屏幕截图是第四层证据，不代替文本完整性比较。

---

## C. PANEL-1 修复 contract

### 身份与回调

以 connection generation、Thread、Turn、Item 组成完整投影身份。history request 还需要自己的 generation。

所有 delta、terminal event、hydrate、异步图像与布局回调都必须绑定正确对象。旧回调不得修改新 Thread、新 Turn 或删除后的 card。

保留已有外围过滤，不增加一套互相矛盾的状态。

### 合并规则

`item/completed` 的完整正文用于收口；迟到 delta 不追加。

不完整 history、summary、notLoaded 不得覆盖完整正文。非原子 snapshot 与 buffered delta 没有可靠边界时不猜着拼接。

已经从 `item/started` 获得完整 live 流的 item，优先保留这条连续事实；中途恢复且无法完整对齐的 item，明确 recovering，等待或定向读取完整终态。

不要通过字符串相似度、前缀或长度去重。

### History 读取

核对固定 0.153.4 的实际 store 支持后，使用 `thread/turns/list`、`thread/items/list` 做局部恢复与分页。只增加必要的 protocol surface。

不支持时采用一次确认后的 fallback；不要每次 delta 都尝试不支持的方法。正常流式消息不触发全历史重读。

分页读只更新所覆盖范围，未加载页面不是删除证据。

### 绘制

数据接收顺序不节流、不丢弃。只合并 UI 绘制：同一 item 在一次短时间窗口内的多个 delta 合并成一次更新，terminal 到达时立即 flush。

初始目标可设为约 50 毫秒的合并窗口，以实际测量调整；不得把这变成额外的模型等待。

长消息必须能完整读取和复制。去除无提示的高度/滚动歧义；先证明 raw text 没丢，再判断 Markdown 和布局是否需要修正。

---

## D. R1 tests / acceptance

添加针对性测试，而不是重复跑一堆无关 Box smoke：

```text
同一 Thread 两轮连续 streaming
A/B/A 切换与迟到 history
连接重建后旧回调
history 在 item/completed 后返回
summary 与 full item 区分
重复事件与合法重复文本
缺失 start / 缺失 terminal / buffer overflow
中文、长代码块、长 Markdown、末尾标记完整性
archive/delete 后旧事件
用户滚动和选择文本时的更新
```

测试比较的是完整 canonical source 与正确的 item 归属。不要把 Markdown 源码和渲染后的 plain text 不同误判为数据丢失。

至少有一个可复现失败在旧代码上失败、新代码上通过；若找到了多个独立缺陷，各自保留最小回归。

真实 Houdini Panel 完成连续对话、切换、重连与长回复检查。**不能只用 offscreen Qt 测试关闭 PANEL-1。**

---

## E. R2 性能 / 模型效率工作

对上述八个 turns 建一个小型本地 call ledger：

```text
call identity
请求目的
读取/修改目标
结果提供的新事实
是否重复已有有效事实
错误与修正
是否真的需要视觉判断
Runtime 耗时与工具间等待
```

把 execute 分成只读 probe、authoring、view preparation、mixed，不允许只按工具名字统计。

审批后的实现范围：

* 合并常驻 instructions 中重复的可靠性解释；
* 明确已知编辑直接做，未知信息再查询；
* 自写 readback 有效时不额外要求 `observe_after`；
* 修具体字段级 schema 错误；
* 统一同类 metadata 分页语义；
* 优化请求内 catalog/help 复用和有界结果构造；
* 保留真实标识、分页、receipt、step gate、unknown 行为。

不得加入“每轮最多 N 次调用”、强制节点路线、强制 staged、强制 capture 或更多历史 bug 专属 prompt 条款。

使用少量代表性请求比较修正前后 cold/warm 耗时。UI 排版、HOM、SQLite、网络和模型思考分别记，不生成一个没有解释力的总“慢”指标。

---

## F. R3 UI refinement

使用现有原生主题和正式 specification。

批准的视觉变化只有：

```text
更明确的用户 / Codex 消息层次
连续 activity segment 的紧凑展示
失败、unknown、partial、重要警告保持可见
真实 staged progress
有限的 Launcher first-run / error refinement
```

可以使用已安装的 `$redesign-existing-projects` 辅助审查。但优先级固定为：

```text
本轮 Pro 决定
→ Studio 正式 UI specification
→ 已批准约束
→ Skill 通用建议
```

**Icon 锁定当前 Lucide 0.468.0 的 23 个已批准资产。**不新增 icon，不换 family，不自绘 Logo，不以 emoji 或 Qt StandardIcon 代替产品资源。现有 QPainter 对批准 SVG 的正常渲染不等于允许手绘新图形。

从实际生产包生成窄/正常 Panel、长对话、审批、失败、运行中、历史恢复和 Launcher 异常状态截图。当前会话未能读取 CI 图片包，所以这些图必须作为本轮实际 review evidence 提供，不能引用旧“已看图”结论代替。

---

## G. R4 Packaging / distribution

独立 branch：

```text
codex/windows-release-package
```

采用 per-user Inno Setup 和目录式私有 runtime；随包固定 Codex，不依赖用户 Python/Node/Git。

构建时锁定 dependency 版本、来源与 hash，保留完整许可证材料。运行时不 pip install、不自动更新工具链、不修改 Houdini Python/Qt。

验证：

```text
无开发 checkout
无全局 PYTHONPATH
安装路径含空格/中文
普通非管理员账号
开始菜单正常启动
私有 Python 的 -m helper / MCP 路径有效
Houdini 不加载私有 Qt
升级保留用户 state 与 native cwd
卸载不删除用户输出
诊断包不含凭证和聊天正文
```

保持现有输出策略。缓存清理不得误删 cache 下的未保存场景作品。

不做大型 updater、不扩平台、不为安装器增加新的后台常驻服务。

---

## H. Reliability / capability invariants

所有阶段必须保留：

**main-thread HOM、单一执行权、durable receipt、scene epoch、步骤检查门、unknown/partial、不盲目重放、capture 恢复和具体授权。**

但这些 invariant 主要由 backend 自动履行。**不得要求模型每次亲自检查所有协议字段，也不得以 hardening 为由缩小合法 HOM authoring 能力。**

不修改历史实验来制造通过。状态应改为：

* TC1：已执行，效率门槛未达到；
* TC2：任务通过，target capture 采用已证实，标准回读采用未证实；
* TC3：staged 与局部恢复、外部 HDA 复用已证实，完整质量/身份连续性未通过。

不能继续登记为 pending official login。

---

## I. Git / merge / release gate

使用语义提交，例如：

```text
fix(panel): fence stream and history items by native identity
perf(panel): coalesce rendering without dropping deltas
perf(lookup): avoid redundant metadata and help work
refactor(instructions): remove duplicate tool-use requirements
feat(ui): present compact chronological Houdini activity
build(release): assemble the pinned Windows runtime package
```

R1–R4 分别通过自己的技术 gate 后合并，不继续顺手塞下一阶段。

**公开 release 的最终 gate：**

> 真实安装包在新用户环境中完成登录、已有 HIP 编辑、视觉反馈、后续修改、保存、关闭、重开、resume 和继续编辑；PANEL-1 关闭；授权不反复打断；长消息完整；错误不被折叠隐藏；没有可重复且未经解释的性能退化；用户数据与合法 authoring 能力都没有被削弱。

**Codex 现在从 `codex/panel-history-correctness` 开工。先把消息链路做对，再降低无效往返、完成界面收口和安装包；这一轮不再增加新的大块工具能力。**

[1]: https://doc.qt.io/QT-6/qtextdocument.html "https://doc.qt.io/QT-6/qtextdocument.html"
[2]: https://openai.com/index/unlocking-the-codex-harness/ "https://openai.com/index/unlocking-the-codex-harness/"
[3]: https://developers.openai.com/codex/app-server/ "https://developers.openai.com/codex/app-server/"
[4]: https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm "https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm"
[5]: https://docs.python.org/3/using/windows.html "https://docs.python.org/3/using/windows.html"
[6]: https://www.sidefx.com/docs/houdini/ref/plugins.html "https://www.sidefx.com/docs/houdini/ref/plugins.html"
[7]: https://doc.qt.io/qt-6.8/licensing.html "https://doc.qt.io/qt-6.8/licensing.html"
