Option Explicit
Dim shell, files, root, python, entry
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(WScript.ScriptFullName)
python = files.BuildPath(root, "runtime\pythonw.exe")
entry = files.BuildPath(root, "start_release.pyw")
If Not files.FileExists(python) Or Not files.FileExists(entry) Then
    MsgBox "Studio installation is incomplete. Reinstall this version or open the previous version.", vbExclamation, "Big-Chicken Houdini Studio"
    WScript.Quit 1
End If
shell.CurrentDirectory = root
shell.Run Chr(34) & python & Chr(34) & " -I -B " & Chr(34) & entry & Chr(34), 0, False
