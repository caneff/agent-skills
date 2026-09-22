' Windows-side handler for herdrfocus:<pane_id> toast clicks. Runs under wscript //B
' so no console window appears. Raises the window hosting herdr, then focuses the
' pane inside herdr.
'
' Window choice and activation both live in herdr-focus-pick.ps1 now (2026-09-17).
' It used to be title-based here via AppActivate, hardcoded to "Visual Studio Code",
' which raised nothing at all once the terminal became WezTerm; and WezTerm retitles
' itself per workspace, so a title read in one step goes stale by the next. The
' picker matches the owning process and calls SetForegroundWindow on the HWND itself.
' HERDR_MARKER (from ~/.config/herdr/host-window) is passed through as a tiebreak
' when that process owns several windows.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
wslHome = "\\wsl.localhost\Ubuntu-24.04\home\caneff"
' The picker sits beside this script; the registry points at this file's real
' location, so its own folder is the install root (no second copy of the path).
binDir = fso.GetParentFolderName(WScript.ScriptFullName)

url = ""
If WScript.Arguments.Count > 0 Then url = WScript.Arguments(0)
pane = Replace(url, "herdrfocus:", "")
pane = Replace(pane, "/", "")

marker = ""
markerFile = wslHome & "\.config\herdr\host-window"
If fso.FileExists(markerFile) Then
  Set f = fso.OpenTextFile(markerFile, 1)
  If Not f.AtEndOfStream Then marker = Trim(f.ReadLine())
  f.Close
End If

Set env = sh.Environment("PROCESS")
env("HERDR_MARKER") = marker
sh.Run "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & binDir & "\herdr-focus-pick.ps1""", 0, True

sh.Run "wsl.exe -d Ubuntu-24.04 -- /home/caneff/.local/bin/herdr-focus-latest " & pane, 0, False
