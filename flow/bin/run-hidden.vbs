' Run a command with no window: wscript //B //Nologo run-hidden.vbs <command line>
Set sh = CreateObject("WScript.Shell")
cmd = ""
For i = 0 To WScript.Arguments.Count - 1
  If i > 0 Then cmd = cmd & " "
  cmd = cmd & WScript.Arguments(i)
Next
sh.Run cmd, 0, False
