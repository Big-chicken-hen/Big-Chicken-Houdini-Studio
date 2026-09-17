**我重新查了最新记录、Studio 启动源码，以及 PySide6／Qt WebEngine 的上游实现。现在可以比上一轮更明确地说：问题更像是 Houdini 的内置浏览器没有正常完成初始化，而不是帮助文档本身打不开。**

**Studio 把 Launcher 的部分运行环境一路传给 Houdini，是目前最值得验证的触发来源；但还不能把某一个 PATH 项认定为已经证实的根因。**

## 1. 最新证据已经缩小了问题范围

仓库已经前进到 **`963ea3e`**，新增了真正运行中的 Houdini GUI 对照，不再只有后台 DLL 检查：

| 实际观察             | 直接启动 Houdini    | Studio 启动 Houdini      |
| ---------------- | --------------- | ---------------------- |
| Houdini EXE／版本   | 同一个 22.0.368    | 相同                     |
| 用户 preferences   | 原生目录            | 相同目录                   |
| 帮助页类型            | 内嵌 HelpBrowser  | 相同                     |
| 配置的帮助首页          | 本机帮助地址          | 相同                     |
| **当前帮助 URL**     | **正常的首页地址**     | **空字符串**               |
| Qt library paths | Houdini 自己的目录   | 相同                     |
| Studio Panel 模块  | 未加载             | **也未加载，但帮助已经坏了**       |
| WebEngine 子进程    | 观察到存活的 renderer | **观察到六次启动，随后查询时均已不存在** |

这些都已写入新的 GUI 验证记录。**六次启动后查不到进程，还不能直接称为“崩溃六次”——没有拿到退出码和进程角色。**但它比“PATH 中有一个 PySide6 目录”更接近故障发生的位置。

由此可以先排除几个不准确的方向：

**不是必须打开 Studio Panel 才会触发。**这一轮 Panel 模块还没加载，问题就已存在，因此不应继续优先排查 Panel 配色、消息渲染或 Composer。

**不是“原生从 Houdini bin 启动，所以能找到 DLL”这么简单。**真实原生基线的 cwd 是 `C:\Users\Administrator`，并不是 Houdini 的 `bin`。此前这种解释没有得到现场支持。

**也不能直接归咎于 Clash。**现有服务读取成功，加上空 URL、缺导航和浏览器子进程异常线索，更应该先调查浏览器初始化；并不是已经证明代理绝无影响。

---

## 2. 我查到了 Launcher 私有 PySide6 路径进入 Houdini 的具体来源

这次不只是看到“环境不一样”，而是找到了它怎样产生、怎样传播。

### PySide6 导入时，会主动修改 Windows 的 PATH

**PySide6 6.8.3 的官方初始化代码**里就有这一句：

```python
os.environ['PATH'] = os.fspath(pyside_package_dir) + os.pathsep + os.environ['PATH']
```

也就是说，Launcher 导入自己的 PySide6 后，会把它的包目录加到当前进程 PATH 前面。这是 PySide6 为自身插件加载做的处理，并不是用户手工配错。

### Studio 随后保留了这个 PATH

当前 `helper_environment()` 从已经运行的进程环境复制：

```python
env = dict(os.environ)
```

它清理一部分 `QT_`、Python、Houdini 变量，但**没有撤掉 Launcher 导入 PySide6 时加入的 PATH 项**。`launcher_environment()` 和 `child_environment()` 继续使用这个结果；最终 supervisor 又把自己的环境传给 Houdini。

因此，下面这条继承链是有源码依据的：

> **Launcher 导入私有 PySide6 → PATH 被追加私有 Qt 目录 → supervisor 继承 → Houdini 继承 → 可能继续影响它启动的浏览器辅助进程。**

最后一步中的“是否实际影响浏览器”尚未证明，前面的环境传播已经确认。

### 为什么“Houdini 已加载正确 Qt DLL”仍然不能结束检查？

因为 `houdini.exe` 和 `QtWebEngineProcess.exe` 是不同进程。**Houdini 主进程已经加载的 DLL 列表，不是浏览器子进程的 DLL 列表。**

Windows 对依赖 DLL 的解析还涉及可执行目录、加载策略和 PATH 等因素；即使一个入口 DLL 使用了完整路径，其依赖仍可能按模块名继续解析。([微软学习][1])

不过，也要保留反证：最新快照显示，**Houdini 已把自己的目录放在那个 Launcher PySide6 项之前**。所以现在不能直接跳到“浏览器肯定加载了错误 Qt”。

**我的判断是：这是一个明确存在、值得做单变量验证的环境继承问题，不是已经结案的混 DLL 故障。**

---

## 3. 为什么现有检查一直没有抓到真正原因？

主要有两处没有打到故障点。

### 一是一直在看主进程的“配置路径”，还没拿到浏览器实际选择的路径和退出原因

我查了 **Qt WebEngine 6.8.3 源码**：辅助程序路径首先从 `QLibraryInfo` 等候选位置解析，或者使用显式的 `QTWEBENGINEPROCESS_PATH`。**它不是简单地在 PATH 中搜索一个同名 EXE。**

而且源码已经提供专门的日志分类：

```text
qt.webengine.libraryinfo
```

开启后会直接打印实际选中的 WebEngine process、resources、locales 路径。**这比等进程启动后再去查询其路径可靠得多，尤其适合目前“进程很快就查不到”的情况。**

当前准备的日志方案主要覆盖 `qt.webenginecontext`、QML imports 和 Qt plugins，应该补上这个分类。

### 二是只捕获了启动，随后再查询进程，错过了退出信息

这里不需要不断提高轮询频率。

Windows 的 **`Win32_ProcessStopTrace` 本身就带 `ProcessID`、`ParentProcessID` 和 `ExitStatus`**。在复现前订阅结束事件，可以在进程已经结束之后仍取得退出状态，不必依赖 `Get-Process` 恰好赶上它活着的瞬间。([微软学习][2])

这能把当前的：

> “启动过，后来找不到。”

推进到：

> “启动的是哪个辅助程序，以什么角色运行，正常退出还是异常退出，退出时报告了什么。”

### 另一个可以降级的怀疑：XDG

我也查了 Qt 6.8.3 的 Windows 实现：`QStandardPaths` 的主要配置／缓存位置通过 Windows Known Folder 接口取得，临时目录则另走 `QDir::tempPath()`。**不能仅因看到 `XDG_*` 指向 Studio，就断言 Windows 的 Qt WebEngine profile 被它重定向了。**

所以，`XDG_*` 不应与实际可疑的辅助进程退出线索同等优先；`TEMP/TMP` 的影响仍需要另行验证。

---

## 4. 下一次让 Codex 做什么

**不要继续查“DLL 文件在不在”，也不要继续跑独立 offscreen 浏览器。下一次真实 GUI 复现只补这组关键证据：**

### 先记录一次没有改变运行行为的失败

在最终传给 Houdini 的**子进程环境副本**中，临时追加以下日志设置，保留原有 logging rules：

```text
QT_FORCE_STDERR_LOGGING=1

QT_LOGGING_RULES 追加：
qt.webenginecontext.debug=true
qt.webengine.libraryinfo.debug=true
```

必要时再追加 Chromium 的官方日志参数：

```text
QTWEBENGINE_CHROMIUM_FLAGS：
--enable-logging --log-level=0
```

这些只是诊断选项；不加 `--no-sandbox`、`--single-process` 或禁用 GPU。Qt 官方支持这些日志入口。([Qt 文档][3])

同时在打开帮助前捕获对应进程的 start／stop，重点取得退出状态。**不改全局环境，不动 Clash，不改变 workspace cwd。**

### 再做一个最有区分度的对照

如果日志没有已经指出明确错误，下一次仅在 Houdini 子进程的 PATH 副本中移除这一条**已确认由 Launcher 加入的目录**：

```text
E:\Big-Chicken-Houdini-Studio\
.runtime\venv\Lib\site-packages\PySide6
```

其他 Houdini 路径、用户插件路径、TEMP、cwd、preferences、Studio Runtime 全部保持相同。

**这是一项诊断对照，不是直接批准永久删除用户 PATH。**

* 帮助恢复：再把该项恢复，确认故障回来，才有理由把修复落在这条继承边界。
* 帮助仍空白：停止执着于这个 PATH 项，依据捕获的 WebEngine 错误判断资源、临时目录／权限或 Runtime 初始化影响。
* 发现 Runtime 自启才是必要触发条件：再做同环境下的单独自启对照，不把 Panel 模块没有加载误解为“所有 Studio 代码都已排除”。

**现在已经不缺一份更长的排查清单，缺的是浏览器辅助进程的实际路径、启动错误和退出状态。**

---

**回答你“为什么会出现”：目前最有依据的解释是，Studio 改变了 Houdini 的启动环境，使内置 WebEngine 的初始化／辅助进程链在这一启动方式下没有正常工作。文档服务仍在，所以能拿到 HTML；但负责显示它的浏览器没有正常进入页面，最终只剩空白窗口。这个机制判断有新证据支持，具体是哪一个环境项或启动副作用，还需要上面的一次真实 GUI 对照才能定案。**

[1]: https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order "Dynamic-link library search order - Win32 apps | Microsoft Learn"
[2]: https://learn.microsoft.com/en-us/previous-versions/windows/desktop/krnlprov/win32-processstoptrace?utm_source=chatgpt.com "Win32\\_ProcessStopTrace class | Microsoft Learn"
[3]: https://doc.qt.io/qt-6.8/qtwebengine-debugging.html "Qt WebEngine Debugging and Profiling | Qt WebEngine 6.8.8"
