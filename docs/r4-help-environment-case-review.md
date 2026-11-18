**我找到一个具体的源码级问题了：很可能不是 PATH 里“多了哪个目录”，而是环境变量的名字从 `Path` 变成了 `PATH`，随后被 Qt WebEngine 的 Chromium 沙箱过滤掉了。**

**过滤代码的问题我已经独立复现；它是否就是你这台 Houdini 的最终根因，还需要一次真实 GUI 修正验证。**但现在已经有明确的触发链和很小的修正点，不必继续盲查 DLL、QML、Clash。

## 1. 问题出在 `Path` 和 `PATH` 的大小写

### 第一环：Python 在 Windows 上把环境变量名转为大写

Python 官方文档明确说明，Windows 上 `os.environ` 的键会转为大写。因此：

```text
Windows 原始环境中的 Path
             ↓
       dict(os.environ)
             ↓
            PATH
```

同样：

```text
SystemRoot  → SYSTEMROOT
SystemDrive → SYSTEMDRIVE
```

这不是路径内容变了，而是**变量名的拼写变了**。([Python 文档][1])

Studio 最终启动 Houdini 的代码，恰好使用：

```python
process = subprocess.Popen(
    command,
    env=dict(os.environ),
    ...
)
```

也就是在最后一道宿主启动边界，重新把 Python 环境字典序列化给 Houdini。位置在当前 `src/studio/launcher.py` 的 `supervise()`，约第 355 行。

### 第二环：Qt 6.8.3 的 Chromium 会过滤 renderer 的环境

我沿着 **Qt WebEngine 6.8.3 实际引用的 Chromium 子模块**查了下去，不是拿最新 Chromium 猜旧版本行为。

其 renderer 启动代码明确开启：

```cpp
config->SetFilterEnvironment(/*filter=*/true);
```

随后创建浏览器子进程时，只保留一个固定名单，其中写的是：

```cpp
L"Path",
L"SystemDrive",
L"SystemRoot",
L"TEMP",
L"TMP",
L"LOCALAPPDATA",
L"CHROME_CRASHPAD_PIPE_NAME"
```

注意：前三项不是全大写。

### 第三环：过滤函数居然按大小写精确匹配

真正关键的是这里：

```cpp
if (std::find(to_keep.begin(), to_keep.end(), key) != to_keep.end()) {
    result.append(ptr, line_length);
}
```

**它没有做大小写无关比较。**

于是，在这段代码眼里：

```text
Path       → 保留
PATH       → 丢弃

SystemRoot → 保留
SYSTEMROOT → 丢弃
```

这就是当前值得优先修正的兼容性陷阱。

---

## 2. 我已经把这段过滤逻辑单独编译运行了

我在当前环境中提取了对应的字符串解析与过滤逻辑，**保持变量值完全相同，只改变键名大小写**，得到：

| 输入环境形式      | `Path` 保留下来 | `SystemRoot` 保留下来 | `SystemDrive` 保留下来 | `TEMP` 保留下来 |
| ----------- | ----------: | ----------------: | -----------------: | ----------: |
| 原生常见拼写      |           是 |                 是 |                  是 |           是 |
| Python 大写键名 |       **否** |             **否** |              **否** |           是 |
| 只恢复前三项键名    |           是 |                 是 |                  是 |           是 |

**这是我实际运行的过滤逻辑测试，不是 Houdini GUI 测试，也不是 Codex 的报告。**

因此现在的高可信故障链是：

> **Studio 用 Python 重建环境 → `Path` 变成 `PATH` → Houdini 本身仍能使用它 → Chromium 创建 renderer 时按大小写过滤 → renderer 丢失 DLL 搜索路径 → 某个必要依赖无法加载 → `0xC0000135` → 内置帮助空白。**

微软对 `0xC0000135` 的定义正是 **`STATUS_DLL_NOT_FOUND`**，不是 HTTP 错误，也不是普通页面渲染超时。它可以涉及入口 DLL 或其依赖，**我不会在没拿到加载记录时硬说缺的一定是 `Qt6WebEngineCore.dll`。**([微软学习][2])

## 3. 它能解释为什么此前的检查都“看起来正常”

### Houdini 主进程的 Qt 路径正确，为什么帮助仍坏？

因为过滤发生在 **Houdini 再创建浏览器子进程**的时候。

主进程能加载 Houdini 自己的 Qt，不代表子进程在经过过滤后仍拥有相同的搜索环境。Windows 的 DLL 依赖解析会使用子进程自己的搜索条件，PATH 是其中一部分。([微软学习][3])

### 手工启动 `QtWebEngineProcess.exe` 为什么可以退出 0？

直接启动没有证明它经过了 Chromium 的这段 renderer 沙箱环境过滤。因此，**那个测试不能覆盖目前找到的失败条件**。renderer 的正式启动路径确实会开启环境过滤。

### 为什么检查出来“两边都有 PATH”，却一直找不到差异？

**因为当前诊断脚本本身也是从 `os.environ` 读取的。**

它会把原生进程里的 `Path` 同样显示成 `PATH`。换句话说，**这份诊断输出可能把我们需要观察的键名差异抹掉了**；只比较路径值，当然看不出来。 ([Python 文档][1])

要观察这个差异，应读取实际 Win32 环境块的原始键名，例如 `GetEnvironmentStringsW()`，而不是再做一次 `dict(os.environ)`。微软明确提供这个原始环境块接口。([微软学习][4])

### 为什么追加 Qt 日志仍未必能报出缺哪个 DLL？

如果依赖加载在程序正常初始化前就失败，Qt 自己的日志代码可能还没机会工作。**这与你截图里的固定加载失败码相符，但退出码本身仍不包含 DLL 名称。**

所以现在不应再以“Qt 日志没写出 DLL 名称”为理由停住。

---

## 4. 最小修正点已经明确：最后一次 `Popen`，只恢复键名

**我上一条把 Launcher 私有 PySide6 目录列为首要对照，现在修正优先级：先不删除任何 PATH 目录，先验证环境变量名大小写。**

在 `supervise()` 最终启动 Houdini 的位置，把直接传入的 `dict(os.environ)` 换成下面这个普通字典：

```python
host_env = dict(os.environ)

if os.name == "nt":
    # Preserve values exactly; restore spelling expected by
    # the Qt 6.8.3 Chromium renderer environment filter.
    for native_name in ("Path", "SystemRoot", "SystemDrive"):
        upper_name = native_name.upper()
        if upper_name in host_env:
            host_env[native_name] = host_env.pop(upper_name)

process = subprocess.Popen(
    command,
    env=host_env,
    cwd=paths.workspace(config["workspace_id"]) / "work",
    stdin=subprocess.DEVNULL,
    stdout=log,
    stderr=log,
)
```

**这段修正不改任何路径值，不增删 DLL 目录，不改 cwd、preferences、插件配置、Clash 或 sandbox。**它只改变传给新进程的三个环境键名。

我也核对了 CPython 的 Windows `CreateProcess` 环境序列化：它对传入 mapping 做排序和去重，但写入环境块时保留键的拼写。因此，**普通 `dict` 中的 `Path` 可以传下去，不会在这个序列化步骤再被统一大写。**

两个位置上的陷阱必须避开：

**不能写成 `os.environ["Path"] = ...`。**Windows 上 Python 又会把这个键规范化成 `PATH`。

**不能只在最前面的 Launcher 改一次。**后面的 Python supervisor 再次 `dict(os.environ)`，仍会把拼写变回去。应当在**最终启动 Houdini 的 `Popen` 前**处理，并直接传入该字典。([Python 文档][1])

---

**现在我的结论不再是笼统的“可能环境污染”：我已经找到了 Python 环境变量名规范化与 Qt 6.8.3 Chromium 大小写敏感过滤之间的具体冲突，并复现了它会丢掉 `Path`。**

我还没有在你的 Windows 上执行这段修正，也未验证 SideFX 随包二进制是否对该上游代码做过补丁，因此不会宣称现场已经修好。**但下一次验证已经可以非常直接：路径内容全部不动，只在最终 `Popen` 恢复这三个键名，重新打开真实 Houdini 帮助。**先检验这条明确的故障链，不再继续撒网查 DLL、重装 Qt 或等待更多泛化日志。

[1]: https://docs.python.org/3.13/library/os.html?utm_source=chatgpt.com "os — Miscellaneous operating system interfaces — Python 3.13.15 documentation"
[2]: https://learn.microsoft.com/fr-fr/openspecs/windows_protocols/ms-erref/596a1078-e883-4972-9bbc-49e60bebca55?utm_source=chatgpt.com "[MS-ERREF]: NTSTATUS Values | Microsoft Learn"
[3]: https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order "Dynamic-link library search order - Win32 apps | Microsoft Learn"
[4]: https://learn.microsoft.com/en-us/windows/win32/procthread/environment-variables "Environment Variables - Win32 apps | Microsoft Learn"
