# PR #5 closure and existing-HIP authoring direction

Latest user-supplied Pro approval, 2026-09-06, reviewed head
`06b2c5c9620e13d87c8c13e0683b1eab7f239d88`.
This approval freezes PR #5 features and supersedes the earlier presentation
brief's construction stages and acceptance gate. The approved page structure,
pink visual direction, 23 Lucide assets and native architecture remain in force.

The merge gate is one compact real workflow: official browser login and matching
Launcher/production account; first use; real Panel Chinese IME and text/image
clipboard input; native model/effort and consent grant, reuse and revoke; one
small edit, production capture and another edit of the same asset; actual
Save/Save As, Recent reopen and continued editing; and one bounded running-HOM
Stop check. Record image delivery and model use of that image separately.

Cross-monitor DPI remains unverified unless actually checked. Lack of a complete
monitor/DPI matrix does not by itself block merging. Observed wrong click
coordinates, an off-screen model popup or an inaccessible Stop control are
correctness defects and do block merging. CI and offscreen fixtures do not
replace the real workflow. Do not carry this gate to another PR.

The operative execution brief below is preserved from the supplied review.
Next-stage implementation starts only after PR #5 closes and merges; the future
branch is `codex/scene-authoring-quality`, created from the resulting main.

# 第六部分｜Codex Execution Brief

## 任务：先结束 #5，再交付既有 HIP 的可维护程序化编辑

### Role

Pro 本轮只做独立审查、审批和方向制定，没有修改仓库。

Codex负责实施、回归测试、整理最小证据和提交。浏览器认证、真实输入法和鼠标交互等必须由普通 UI 完成的步骤，由用户或测试者操作；Codex不得用禁止的自动化路径替代并宣称验收成功。

---

## A. Baseline：先确认最新状态

```text
Repository:
Big-chicken-hen/Big-Chicken-Houdini-Studio

Reviewed main:
557a393e70c5f6f96d2a8e60e7428b243b29e39e

PR #5:
codex/ui-productization

Reviewed head:
06b2c5c9620e13d87c8c13e0683b1eab7f239d88

Old HIA:
6d9a2d7b606d699fc85bf13586d31aa27455a63b
```

确认远端 head、CI 对应提交和 working tree。后续已有工作不得为了匹配本 Brief 的 SHA 被回退。

**立即冻结 #5 的新增功能范围。**

---

## B. PR #5：执行一轮集成验收，不继续写新框架

### 流程一：首次使用与连续小编辑

使用隔离的测试用户状态，不清除真实用户认证或旧数据。

正常打开 Launcher，完成官方浏览器登录，进入 Home，Start Empty，打开真实 Panel。

使用 Microsoft Pinyin 输入一个小型节点任务，包含参数修改和必要回读。附加一张图片或 selection，确认模型设置、许可和返回内容。下一轮要求修改同一对象，确认不重复创建。

截图必须通过生产 capture 路径返回模型和 Panel。**“显示了一张图片”与“模型确实依据图片判断”分别记录。**

### 流程二：文件身份与 returning user

保存为 `A.hip`，Save As 到另一个测试目录的 `B.hip`。

确认当前 HIP 展示、Recent 关联、后续默认输出位置正确；活跃 workspace、ledger 和 native cwd 不被移动；用户已有输出参数不被静默改写。

退出、重新打开 Launcher，从 Recent 打开 B，恢复或选择原生对话，再完成一个小修改。

### 流程三：一次有界 Stop

先确认 execute 已进入 running，再从真实 Panel 请求停止。

记录请求是否可达、何时送达、是否阻止后续工作、原 operation 最终状态。不可中断原生调用可按已知限制记录；重复副作用、错误终态和收据丢失必须修复。

**不追求通用 Python/HOM 强制抢占，不引入后台任意 `hou` 调用。**

### 缺陷处理规则

遇到明确缺陷，修一个真实行为并补相应回归，再重跑受影响片段。不要每次文案修改都重新建立完整证据包。

没有真实失败时，不主动增加“更稳健”的新抽象。

完整跨屏 DPI 矩阵不再无条件挡合并；有实际裁切、错误点击或关键控件不可达时，按普通 correctness 缺陷处理。同步更新文档，不把未验证改写成通过。

---

## C. #5 收口与 Git

满足上述收敛后的 Gate、最终候选 CI 有效、无未解决的确定 blocker 后，提交简短验收结果，结束 Draft，并按正常审批流程合入 `main`。

**不要把用户验收再次转移到下一 PR，也不要等下一项 Houdini 能力开发完才合并 #5。**

当前远端仍留有已完成的 `codex/authoring-cycle` 和 `codex/usable-authoring-integration` 分支。确认其提交已被主线包含、没有独有工作后清理即可，不重写公开历史。

#5 合并后，从最新 `main` 建立一条短期分支：

```text
codex/scene-authoring-quality
```

只承载下一阶段的程序化编辑质量，不再叠加在未收口的 UI 分支上。

---

## D. 下一阶段先读取 Copy Stamp 的实际现场，不按印象改系统

从允许访问的原生会话、操作收据和测试 HIP 中确认：

**请求是什么；哪个脚本创建或引用了哪个精确节点类型；它是新增还是既有；是否使用 stamp 表达式；此前做过什么查询；错误或绕路发生在哪。**

若现场不可取得，保留“根因未确认”，不要把“训练记忆旧”写进结论。

这项追踪用于校准实现与验收，**不阻止已明确缺失的节点元信息补强**。

---

## E. 只补现有 lookup 的缺失信息

优先修改现有：

```text
src/studio/scene.py       # 节点 lookup
src/studio/mcp.py         # 同一工具的参数与描述
src/studio/instructions.py
```

不创建 `hia_modern_node`、`hia_deprecation_check` 或 `hia_validate_workflow`。

### E1. 节点状态

对目标节点返回精确类型与类别、可取得的命名空间信息、`deprecated`、`hidden` 和有来源的弃用说明。

`deprecationInfo()` 返回的替代 NodeType 转成明确的类别与名称，不能直接序列化为无意义的对象 repr。未取得时返回未知，不默认安全。

**隐藏不等于弃用，节点类型版本不等于 Houdini 应用版本。**

搜索中保持精确匹配可靠，不让宽泛查询的前 80 个结果静默冒充完整列表。可做小型排序与截断说明，但不扩成搜索服务。

对 legacy 精确查询必须仍能取得原节点；不能全局过滤掉弃用节点，导致旧 HIP 无法被理解。

### E2. 节点帮助

在同一个 lookup 内提供按需、短的帮助内容与来源。优先实际安装的嵌入/本地帮助，保留版本信息。

只读被请求的节点，不递归扫描整个安装，不启动向量构建，不默认联网抓取任意 HDA 提供的 URL。来源不受控或帮助不可用时明确说明，再由现有研究路径处理。

查询结果是参考资料，不是新的系统指令来源。

### E3. Instructions

用一小段规则明确：

**新建网络优先当前支持的合适流程；维护旧网络优先行为不变；弃用信号触发有针对性的核对，而不是自动替换；简单已知编辑继续走短路径。**

不要把这段规则扩成几十个节点的提示词清单。

---

## F. 旧 HIA：先读这些，再决定提取多少

```text
houdini_package/python_libs/hia_mcp_runtime/executor.py

_node_type_catalog
_node_type_matches
_node_help_result
_parameter_templates
_parm_record
```

处理方式：

| 旧资产                                         | 本轮使用方式                                     |
| ------------------------------------------- | ------------------------------------------ |
| `_node_type_catalog` / `_node_type_matches` | 提取原生类型信息和查询区分，不迁全量 catalog 架构              |
| `_node_help_result`                         | 借鉴来源、类型身份和帮助位置的组织方式；核实哪些实际是正文，哪些只是链接       |
| `_parameter_templates`                      | 保留实例名与模板模式、multiparm 的正确区分；已迁入部分不重复实现      |
| `_parm_record`                              | 对编辑涉及的少数参数检查原始引用/时间依赖，避免把表达式直接烘成常量         |
| 相关旧测试                                       | 查找对应符号，迁移有价值的场景，不把 fake 测试描述成真实 Houdini 证明 |

不要把旧 executor 作为 Studio 的依赖。不要迁回全量 Context Pack、默认语义验收、恢复规划、embedding 或旧兼容后端。

---

## G. 唯一 capability 交付：继续现有资产，完成程序化变化

使用已有书架或相近资产的 HIP 副本，不默认新建一个与现场无关的 demo。

建议真实请求顺序：

**第一步：** 保留外框、已有命名和无关对象，把层板/隔间变成可调整数量与布局的结构。

**第二步：** 用户改变总宽度、层数或间距，Codex利用已有控制继续修改。

**第三步：** 用户要求局部不同深度、偏移或非对称分区，保留前一步结果，并用图像确认。

**第四步：** 保存、重开；用户手动改变一个参数后，再要求一个小修改，检验现场事实优先于旧会话假设。

实现允许局部拓扑调整，但不能每次删除整件资产再用同名根节点重建。也不要求一律封装完整 HDA。

验收看实际网络与输出：

**控制可用、参数引用合理、没有破坏不相关工作、图像与几何事实一致、重开后可继续编辑。**

另用一个小型 legacy 场景做保护性检查：场景含旧节点时，Agent 能查明它并按任务编辑，不擅自迁移。只有用户明确要求现代化，才执行行为对照后的迁移。

---

## H. Authoring rhythm 与最小性能记录

工作节奏固定为：

**必要的定向观察 → 一个或少数语义批次 → 批次内回读 → 有价值的视觉反馈 → 用户下一次修改。**

不规定所有任务固定经过所有工具。已知宽度参数无需重新搜索；真正改变复制策略或陌生 API 时，再查询安装信息。

每轮只记录：

**模型工具序列、审批等待、端到端时间、Runtime 排队/执行/capture 时间、失败与修正次数、最终保留的场景结果。**

内部 receipt 轮询不算模型 reasoning 轮次；无法拆开的推理/网络等待就保留组合值，不编造精确归因。

一次调用可能完全值得，一次错误也可能合理。重点检查反复猜同一 API、反复全量 inspect、忽略已取得的类型信息和失败后重建全部资产。

---

## I. Skills、UI 与图标硬约束

默认不调用 `$redesign-existing-projects`，不安装其他 UI Skill。

真实 UI blocker 需要局部修复时，先读本 Brief 和正式规范，再读本机 Skill；只借鉴层级、状态和密度检查。不得改页面结构、换字体体系、增加装饰背景或更换图标来满足通用设计建议。

**Codex 不得自行设计、发明、选择或替换正式产品 icon。** 保留已批准 Lucide 子集；没有资产就使用文字。

不新增 Web frontend、Electron、全局状态框架、权限平台或验证平台。

---

## J. 提交与完成标准

#5 只保留实际缺陷提交和一次最终验收记录，不创建 `polish` 系列。

下一阶段可按实际语义形成：

```text
feat(lookup): expose installed node status and targeted help
fix(authoring): distinguish new workflows from legacy maintenance
test(authoring): verify iterative procedural editing in an existing HIP
```

若实际工作暴露生产缺陷，按具体行为追加修复；没有缺陷就不为凑提交增加代码。

**下一阶段完成，不是 lookup 字段上线，而是用户真的能在既有 HIP 中完成一段可维护的程序化编辑。**

---

**最终审批：当前架构继续，UI 停止大改，#5 固定候选后完成一轮真实收口；下一条分支只做既有 HIP 的程序化编辑质量。**

**Copy Stamp 不应让 Studio 回到黑名单或知识平台建设，也不应该被轻描淡写地归为模型偶发失误。正确做法是补回已经有依据的少量节点信息，让 Codex在真实作品中作出更好的选择，并以作品是否能继续维护来判断进步。**

[1]: https://www.sidefx.com/docs/houdini/nodes/sop/copy "https://www.sidefx.com/docs/houdini/nodes/sop/copy"
[2]: https://www.sidefx.com/docs/houdini/nodes/sop/copyxform.html "https://www.sidefx.com/docs/houdini/nodes/sop/copyxform.html"
[3]: https://www.sidefx.com/docs/houdini/hom/hou/OpNodeType.html "https://www.sidefx.com/docs/houdini/hom/hou/OpNodeType.html"

