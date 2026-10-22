Option Explicit

Dim WshShell, fso, launcherDir, rootDir, scriptPath, cmd, errCode

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
launcherDir = fso.GetParentFolderName(WScript.ScriptFullName)
rootDir = fso.GetParentFolderName(launcherDir)
WshShell.CurrentDirectory = rootDir
scriptPath = launcherDir & "\launcher.py"

' Run with pythonw.exe (no console allocated) and window style 1 (normal visible GUI window)
On Error Resume Next
cmd = "pythonw.exe """ & scriptPath & """"
errCode = WshShell.Run(cmd, 1, False)

If Err.Number <> 0 Then
    Err.Clear
    cmd = "pyw.exe """ & scriptPath & """"
    errCode = WshShell.Run(cmd, 1, False)
End If

If Err.Number <> 0 Then
    Err.Clear
    cmd = "python.exe """ & scriptPath & """"
    errCode = WshShell.Run(cmd, 1, False)
End If

If Err.Number <> 0 Then
    MsgBox "Could not launch Beatbar Suite." & vbCrLf & vbCrLf & _
           "Python executable was not found." & vbCrLf & _
           "Please ensure Python 3 is installed and added to PATH.", _
           16, "Beatbar Launcher Error"
End If
