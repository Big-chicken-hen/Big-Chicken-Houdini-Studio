## 审批结论

**将此问题登记为 `R4-HELP-1：Studio 启动后的 Houdini 内置帮助失效`，按发布前 correctness blocker 处理。**

这里的判断分成两层：

**故障已经成立：**根据你提供的现场记录，同机、同一 Houdini 安装，直接启动正常，经 Studio 启动则重复出现内置帮助空白。这不是“还能优化”的问题，而是 Studio 启动方式可能损害了宿主已有功能。

**根因尚未成立：**目前不能认定是 DLL 缺失、Launcher 的 PySide6 路径、代理、QML、临时目录或某一次提交导致。**下一步批准的是有针对性的同机 GUI 对照，不是先改 PATH 再碰运气。**

我重新核对了仓库：PR #14 仍为 Draft，head 是 **`e686e548352da2de3b742f393c52568df09551d2`**；当前交付候选已是 **`0.1.0-rc.1-8af563981e73`**，不是上轮签字绑定的 `042c66b`。当前包的验证记录也明确：完成了 Launcher 和 headless HDA 检查，**没有完成真实 Houdini GUI 的帮助浏览器验收**。

因此，**暂停当前候选的自动 Ready／merge／Public RC 放行**。可以继续定向诊断，但不能把“安装包尚未复现”解释成“安装包不受影响”。这只是处理一个新发现的具体 blocker，不重新打开其他产品阶段。

---

# 1. 对现有证据的判断

你这份报告对证据边界的划分是正确的，尤其应该保留那两次无效测试的说明，避免它们后来被误当成根因证据。

| 已有观察                             | 可以支持                 | 不能支持                           |
| -------------------------------- | -------------------- | ------------------------------ |
| 帮助首页和节点文档返回完整 HTML               | 帮助服务至少能响应所测请求        | 实际内置浏览器完成了请求、资源加载和渲染           |
| Houdini 已加载的 Qt DLL 来自正确安装       | 已检查到的主进程 Qt 模块来源正确   | QML imports、插件、资源、浏览器子进程也全部正确  |
| 捕获的 PATH 能加载 WebEngine DLL       | 那个测试进程下可以完成该次 DLL 加载 | Houdini 的真实浏览器启动与页面初始化正常       |
| `QtWebEngineProcess.exe` 无参数退出 0 | 可执行文件在该测试条件下能够启动并退出  | Chromium 子进程按 Houdini 实际参数正确工作 |
| 独立进程的 Qt 路径一致                    | 该独立探测结果一致            | 真实空白窗口的有效搜索路径与状态一致             |
| 独立测试连原生基线都退出 139                 | 该测试方法不适合作为当前回归对照     | Studio 造成了这个崩溃                 |

Qt 官方的部署文档也明确区分 WebEngine 库、QML imports、辅助进程、资源和 translations；**一个 DLL 能加载，不等于整条浏览器链已经验证。**([Qt 文档][1])

另外，**“没有地址栏”值得提高 UI 初始化方向的排查优先级，但不能单独证明 QML 加载失败。**Houdini 的 `hou.HelpBrowser.showUI()` 本来就能显示或隐藏导航控件，因此对照必须确认是相同的帮助入口、pane 类型和显示方式，不能只比较两张白色区域。([SideFX][2])

本次我没有访问你 E 盘的 `STATUS.md` 或真实空白窗口；现场结论依据你提交的报告，源码结论依据下面的仓库读取。两者不混写。

---

# 2. 当前启动链确实需要区分“辅助进程环境”和“Houdini 宿主环境”

## 2.1 源码确认：现在只是部分区分，宿主仍继承了辅助环境

当前链路是：

| 位置                       | 实际行为                                                             |
| ------------------------ | ---------------------------------------------------------------- |
| `storage_environment()`  | 设置 Studio 的 TEMP/TMP/TMPDIR、XDG 目录、Python 和内部路径                  |
| `helper_environment()`   | 从当前 `os.environ` 出发，清理若干 Python/Qt/Houdini 变量，再叠加上述设置            |
| `launcher_environment()` | 在 helper 结果上恢复六类 Houdini 搜索路径                                    |
| `child_environment()`    | 继续在该结果上加入 Studio package、session、workspace 与宿主临时目录               |
| `supervise()`            | 最终以 `env=dict(os.environ)` 启动 Houdini，cwd 保持原 workspace 的 `work` |

所以，**恢复六类 Houdini 搜索路径，并不等于已经得到接近原生启动的完整宿主环境**。PATH 没有在这些函数中被重建，辅助进程的存储/Python 设置也继续进入宿主。以上是实际代码事实，不是对故障原因的认定。

还有一个时机问题：开发 bootstrap 在进入 Launcher 前就把 `storage_environment()` 写入当前环境；安装版 bootstrap 则用 `launcher_environment()` 替换环境。**到 supervisor 最后准备启动 Houdini 时，某些原始值可能已经被上游覆盖。**仅在最后增加一个函数名，并不会自动恢复这些值。

## 2.2 最终工程方向：批准区分职责，不批准立即重写环境系统

原则确定为：

> **Studio 辅助程序需要的 Python/Qt 隔离，不应无差别变成 Houdini 宿主的运行环境；Houdini 宿主环境应保留用户原生设置，再叠加必要的 Studio 接入。**

但本轮先证明**哪一项差异实际造成故障**。

若最后只需修正一个已确认错误的路径或变量，就只修那一项。若证据证明当前环境组装顺序无法避免污染，才做小型职责拆分：两种环境字典、明确的组装边界，**不增加进程、服务、配置平台或用户设置页**。

同时，现有六类路径恢复已经修复过真实插件发现问题，不能为了帮助浏览器再全部撤掉，也不能把隔离测试通过作为删除用户路径的理由。

---

# 3. 下一步排查：先取得能区分原因的 GUI 证据

## 第一步：只读检查真实失败窗口

优先使用已经准备的只读脚本，**先审核脚本，再执行**。它只应读取当前帮助窗口，不创建另一个浏览器，不重建 QApplication，不调用 `setLibraryPaths()`、`showUI(True)` 或其他“顺便修复”操作。

对原生正常窗口和 Studio 空白窗口各记录一份：

| 层      | 最小信息                                                                                             |
| ------ | ------------------------------------------------------------------------------------------------ |
| 宿主身份   | 实际 Houdini EXE、版本、PID、cwd、preferences 路径、Studio 是否已加载                                            |
| 帮助对象   | 同一帮助入口、pane 类型、当前 URL、截图；是否存在导航和内容承载对象                                                           |
| Qt 路径  | 实际 GUI 进程中的 `QCoreApplication.libraryPaths()`，以及 `QLibraryInfo` 的插件、QML、辅助程序、资源与 translations 路径 |
| 当前窗口错误 | 若实际承载对象是 `QQuickWidget`，读取其现有 `status()`、`errors()`；能取得已有 QML engine 时读取实际 import path           |
| 浏览器进程  | 从打开帮助前到空白出现后的相关子进程启动、路径、角色、退出和时间顺序                                                               |

**不要新建一个 QQmlEngine，再把它的路径称为“帮助窗口使用的路径”。**`QLibraryInfo` 是 Qt 库信息；已有 engine 的 import path 和实际加载记录是另一层事实。`QQuickWidget` 也提供自己的状态和错误接口，前提是现场确实使用这个对象。([Qt 文档][3])

读取 Qt/HOM 对象必须在 Houdini 主线程完成。对象不可安全取得时就标为 unavailable，**不要靠原始指针包装、全局对象遍历或调用未知 getter 强行补齐**。

## 第二步：必要时在下次真实 GUI 启动时打开有限日志

若现有窗口已经错过初始化错误，才做下一次新进程对照。诊断选项只进入**该次 Houdini 子进程**，并在 Qt 初始化前生效：

```text
QML_IMPORT_TRACE=1
QT_DEBUG_PLUGINS=1
QT_LOGGING_RULES 中增加 qt.webenginecontext.debug=true
```

这是 Qt 官方提供的 import、plugin 和 WebEngine 初始化诊断路径。不是 Chromium 参数试错，也不需要开放远程调试端口。([Qt 文档][4])

有一个本项目特有的注意点：当前 `helper_environment()` 会清理 `QT_` 前缀变量。**只在启动 Studio 前设置这些选项，可能在进入 Houdini 前就被删除。**测试必须确认它们实际到达最后的宿主环境；不要因为日志为空就推断“没有 Qt 错误”。

日志限制在复现窗口内，记录必要路径和错误；不抓取全量认证环境、不永久安装全局 Qt message handler、不改用户的启动配置。

## 第三步：用最少的 GUI 对照定位故障边界

首先固定一个有效的 A/B：

| 组 | 启动方式                     | 其他条件                               |
| - | ------------------------ | ---------------------------------- |
| A | 用户当前确认正常的原生 Houdini 启动   | 同一 EXE、账号、preferences、插件和 Clash 状态 |
| B | 当前 `Studio.exe` 的正式开发启动链 | 同一帮助操作和测试场景                        |

随后**按观察选择下一项，不做所有变量的排列组合**：

* **错误指向资源、QML 或辅助程序路径：**只测试那个路径差异。
* **怀疑 workspace cwd：**让原生正常环境的 Houdini 临时从同一个工作目录启动。它仍正常，就不再把 cwd 当作优先方向；即使发现相关，也不能靠永久改变 native workspace cwd 收尾。
* **环境没有解释力：**在独立测试启动中保持相同宿主环境，只暂时禁用 Studio 自启且不创建其 Panel。核对确实没有加载相关 Studio UI/Runtime 后，再看帮助是否仍坏。这是区分“启动环境”与“宿主内插件副作用”，不是产品新增禁用模式。
* **只有打开 Studio Panel 后才出现：**检查这个时间点实际发生的进程内 Qt 路径、状态或对象变化，而不是继续清理外部 PATH。

对照中每次只改变一个能解释的因素。某项最小修正恢复帮助后，再做一次**撤销修正→复现、重新应用→恢复**。不要求查明 Qt 内部所有机制，但要证明修复与故障确实相关。

**用户现在不方便执行 GUI 脚本，就停在这个具体阻塞点。**Codex 可以先审核现有脚本、整理日志和准备对照；不应继续用失真的 offscreen/hython 测试填充“进展”。

---

# 4. Codex Bounded Fix Brief

## Role / Scope

```text
Pro = 本次故障定性、修复边界和验收审批。
Codex = 本机取证、必要修复、tests、真实 Houdini 验证、
        commit、push、候选重建。

唯一任务：
R4-HELP-1 — 恢复通过 Studio 启动后的原生 Houdini 内置帮助。
```

继续在 PR #14 的现有分支：

```text
codex/windows-release-package

Reviewed head:
e686e548352da2de3b742f393c52568df09551d2

当前交付候选:
0.1.0-rc.1-8af563981e73
```

在 `docs/acceptance-issues.md` 登记当前问题，并关联既有本机：

```text
E:\Big-Chicken-Houdini-Studio\
.runtime\maintenance\help-browser-20260911\STATUS.md
```

状态写清：

```text
开发入口：已复现
原生同安装：报告为正常
发布 payload GUI：尚未确认
引入提交：未知
根因：未知
修复：未实施
发布自动放行：暂停
```

不要因 CI 绿色关闭问题，也不要将它自动归并为此前 R4-NET-1。两者目前没有已证实的共同根因。

## A. 允许的修复范围

首先限于：

```text
启动前的必要环境取值
helper_environment / launcher_environment / child_environment
supervise 的宿主环境传递
必要时开发与 installed bootstrap 的局部接线
对应回归测试
```

若证据明确指向宿主内 Studio 代码，才修那个实际调用点，不强行把所有结果解释为环境问题。

### 若最终证明是 Launcher 私有 Qt 路径泄漏

只处理**能证明由当前 Studio 私有 runtime 带入、且不属于用户原生配置**的项；按路径边界判断，不以包含 `PySide6` 字样就全删。保留用户 PATH 顺序和第三方插件依赖。

若来源必须从 Launcher 导入 Qt 之前区分，就在正确入口保留所需的原始字段，不在已污染的环境上反复推测。**不把完整环境和 token 写入 `launch.json` 或诊断 ZIP。**

### 若证明是必要的原生设置被清理

精确恢复该设置在宿主边界的语义，保留值、顺序及展开标记；普通辅助进程仍使用其原有隔离策略。**不能为了修一项，改成“所有继承变量全部放行”。**

### 若证明是目录、profile 或缓存访问问题

修目录来源或访问条件，不删除用户浏览器缓存、认证、preferences 或 workspace。不把清空目录后第一次能打开当作持久修复。

以上是按证据选择的修复边界，不要求同时实施。

## B. 本轮禁止的“修复”

不得：

* 安装、复制或替换 Houdini 内的 Qt DLL、QML、resources、locale 或 `qt.conf`。
* 把 Studio 私有 Qt 补进 Houdini，让两套 Qt 混用。
* 写死某个 `QtWebEngineProcess.exe` 路径，只因为它单独启动过一次。
* 关闭 Chromium sandbox、切 single-process，或把禁用 GPU 固化为未经证明的默认策略。
* 改全局 PATH、Clash、系统代理或要求关闭 Clash。
* 改用户偏好、插件搜索路径、native workspace cwd 或历史归属。
* 把帮助强制跳转外部浏览器，作为“内置帮助已修复”的交付。
* 通过升级 Houdini、增加模型 prompt、新增 MCP tool 或持续健康轮询绕开问题。

外部浏览器最多是用户临时查看文档的方法，**不计入本问题的验收成功**。

## C. Tests 与真正的验收

自动化测试围绕最终证实的缺陷添加，至少覆盖：

**旧错误条件存在时失败，新修正后通过；开发和 installed bootstrap 均覆盖；原六类 Houdini 搜索路径、preferences、显式测试隔离和 Studio 集成仍保持；环境构造不修改全局 `os.environ` 或用户文件。**

如果修复涉及角色分离，分别断言 helper 与 host 各自拿到哪些必要字段；不要只断言某个新函数被调用。

真实验收必须使用 Houdini **22.0.368 GUI 的内置帮助**：

| 检查        | 通过要求                               |
| --------- | ---------------------------------- |
| 原生基线      | 同一入口的内置帮助首页、节点帮助正常                 |
| 修正后的开发入口  | `Studio.exe` 启动后，导航和正文正常           |
| 继续操作      | 切换节点文档、点击链接、前后导航、关闭后重开帮助仍正常        |
| 冷启动复验     | 至少两个全新 Houdini 进程通过，不只复用已初始化的浏览器   |
| Studio 共存 | Panel 正常打开，做一次小型场景读写后帮助仍正常         |
| 宿主保留      | 原布局、配色、插件路径、HDA 发现、cwd 和历史不受破坏     |
| 退出        | 正常用户窗口关闭，不使用测试专用 `hou.exit()` 强制结束 |

**实际 release payload 还需要独立核对。**Owner 不额外安装产品：可以从当前准确 installer 提取完整 payload 到明确的临时验证位置，经它的 `Studio.exe` 做真实 GUI 检查，并清楚标注这是 payload 验证，**不是标准用户 Installer 验收**。不混用开发 venv 来证明包内运行正常。

所需 GUI 操作要等用户允许的空闲窗口进行，不关闭其未保存工作，不重用其他活跃 workspace 的执行权。

## D. 候选与恢复发布条件

只有调查记录或测试材料变化，且当前包经真实 GUI 被证明不受影响时，**不无意义重建 installer**；若定位为开发依赖的局部问题，应明确修正开发环境，而不是将其扩大成发布包故障。

若修改了生产启动代码、bootstrap 或包内容，则：

```text
局部修复
→ 相关 tests / CI
→ 新 source / builder
→ 新 build ID / installer hash
→ 实际新 payload 的帮助 GUI 验证
→ 更新 Tester ZIP
```

不能继续拿 `8af5639` 的 hash 验收新代码。原失败、无效测试及修复前候选记录保留；无需保留大量重复解包目录。

提交名称按真实原因写，例如：

```text
fix(launcher): prevent private Qt paths from entering the Houdini host
```

**只有确实证明并实施了这类修复，才能使用这个标题。**不要在证据之前用 commit message 锁定根因。

本问题关闭后，恢复原来的有限外部验收→发行路径，只增加“Studio 启动后内置帮助正常”这一项，不重新执行完整 Tool Capability benchmark。

---

**最终方向：先读真实空白窗口的状态与初始化错误，再用同机 GUI 做单变量对照；环境角色应当区分，但只修被证据指向的边界。现在不批准盲改 PATH、不批准补 DLL，也不批准用后台测试宣布帮助恢复。**

[1]: https://doc.qt.io/qt-6.8/qtwebengine-deploying.html?utm_source=chatgpt.com "Deploying Qt WebEngine Applications | Qt WebEngine 6.8.8"
[2]: https://www.sidefx.com/docs/houdini/hom/hou/HelpBrowser.html "hou.HelpBrowser"
[3]: https://doc.qt.io/qt-6.8/qlibraryinfo.html "QLibraryInfo Class | Qt Core 6.8.8"
[4]: https://doc.qt.io/qt-6.8/qtquick-debugging.html?utm_source=chatgpt.com "Debugging QML Applications | Qt 6.8"
