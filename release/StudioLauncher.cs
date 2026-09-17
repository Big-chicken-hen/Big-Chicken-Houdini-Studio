using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;

internal static class StudioLauncher
{
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    private static extern int MessageBox(IntPtr parent, string message, string title, uint flags);

    [STAThread]
    private static int Main()
    {
        try
        {
            string root = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            bool installed = File.Exists(Path.Combine(root, "release-manifest.json"));
            string python = Path.Combine(root, installed ? @"runtime\pythonw.exe" : @".runtime\venv\Scripts\pythonw.exe");
            string entry = Path.Combine(root, installed ? @"runtime\start_release.pyw" : @"scripts\launch_window.pyw");
            if (!File.Exists(python) || !File.Exists(entry))
                throw new IOException("Studio runtime or entry is missing.");
            var info = new ProcessStartInfo(python);
            info.Arguments = (installed ? "-I -B " : "-B ") + "\"" + entry + "\"";
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.WindowStyle = ProcessWindowStyle.Normal;
            info.EnvironmentVariables["HIA_PROJECT_ROOT"] = root;
            info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
            info.EnvironmentVariables["PYTHONNOUSERSITE"] = "1";
            if (!installed)
            {
                info.EnvironmentVariables["BCS_DATA_ROOT"] = Path.Combine(root, ".runtime");
                info.EnvironmentVariables["BCS_CACHE_ROOT"] = Path.Combine(root, @".runtime\cache");
                string codex = Path.Combine(root, @".runtime\toolchains\codex\bin\codex.exe");
                if (File.Exists(codex)) info.EnvironmentVariables["BCS_CODEX_PATH"] = codex;
            }
            using (var child = Process.Start(info))
            {
                if (child == null) throw new IOException("Studio could not start.");
                if (child.WaitForExit(1000) && child.ExitCode != 0)
                    throw new IOException("Studio exited during startup.");
            }
            return 0;
        }
        catch
        {
            MessageBox(IntPtr.Zero, "Studio 未能启动。请保留现场并检查此目录内的运行文件。", "Big-Chicken Studio", 0x10);
            return 1;
        }
    }
}
