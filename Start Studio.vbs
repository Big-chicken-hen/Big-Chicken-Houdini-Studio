Option Explicit
Dim shell, files, root, python, script, processEnv
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
Set processEnv = shell.Environment("PROCESS")
root = processEnv("HIA_PROJECT_ROOT")
If Len(root) = 0 Then root = files.GetParentFolderName(WScript.ScriptFullName)
python = files.BuildPath(root, ".runtime\venv\Scripts\pythonw.exe")
script = files.BuildPath(root, "scripts\launch_window.pyw")
If Not files.FileExists(python) Then
    MsgBox "Run Setup Studio.cmd once before starting Studio.", vbExclamation, "Big-Chicken Houdini Studio"
    WScript.Quit 1
End If
shell.CurrentDirectory = root
processEnv("HIA_PROJECT_ROOT") = root
processEnv("PYTHONDONTWRITEBYTECODE") = "1"
shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & script & Chr(34), 0, False
