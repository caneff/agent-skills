# Windows-side half of the herdrfocus: toast click. Finds the window hosting
# herdr and brings it to the foreground itself.
#
# Terminal choice (2026-09-17): the old version matched titles containing
# "Visual Studio Code", so after the move to WezTerm a toast click raised
# nothing at all. Match the OWNING PROCESS instead — one of $env:HERDR_HOSTS
# (default "Zed,wezterm-gui,WindowsTerminal,Code") in that order of preference;
# Zed leads since herdr moved into its terminal later the same day —
# and treat $env:HERDR_MARKER as a tiebreak among that process's windows, not
# a filter. A host with one window therefore works with no marker in its title,
# which WezTerm's is (herdr sets it to the workspace name).
#
# Activation happens here, by HWND. AppActivate took a title, and WezTerm
# retitles itself on every workspace switch, so the title could go stale
# between pick and activate. Foreground rights are borrowed from the current
# foreground thread (AttachThreadInput) because Windows otherwise refuses a
# background process's SetForegroundWindow.
#
# Writes the chosen window's title to $env:HERDR_OUT when it activated one,
# and nothing at all when no host window exists.

Add-Type @"
using System; using System.Text; using System.Runtime.InteropServices; using System.Collections.Generic;
public class HerdrWin {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool attach);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();

  public class Win { public IntPtr H; public string Title; public uint Pid; }

  public static List<Win> Windows() {
    var r = new List<Win>();
    EnumWindows((h, l) => {
      if (!IsWindowVisible(h)) return true;
      var sb = new StringBuilder(512);
      GetWindowText(h, sb, 512);
      if (sb.Length == 0) return true;
      uint pid; GetWindowThreadProcessId(h, out pid);
      r.Add(new Win { H = h, Title = sb.ToString(), Pid = pid });
      return true;
    }, IntPtr.Zero);
    return r;
  }

  // SW_RESTORE a minimized window, then take the foreground thread's input
  // queue so SetForegroundWindow is allowed to succeed.
  public static bool Raise(IntPtr h) {
    if (IsIconic(h)) ShowWindow(h, 9);
    uint fgPid;
    IntPtr fg = GetForegroundWindow();
    uint fgThread = GetWindowThreadProcessId(fg, out fgPid);
    uint me = GetCurrentThreadId();
    bool attached = (fgThread != me) && AttachThreadInput(fgThread, me, true);
    BringWindowToTop(h);
    bool ok = SetForegroundWindow(h);
    if (attached) AttachThreadInput(fgThread, me, false);
    return ok;
  }
}
"@

$hosts = if ($env:HERDR_HOSTS) { $env:HERDR_HOSTS } else { 'Zed,wezterm-gui,WindowsTerminal,Code' }
$hostNames = $hosts -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
$marker = $env:HERDR_MARKER

$windows = [HerdrWin]::Windows()
$byPid = @{}
foreach ($p in Get-Process) { $byPid[[uint32]$p.Id] = $p.ProcessName }

$target = $null
foreach ($name in $hostNames) {
  $mine = $windows | Where-Object { $byPid[$_.Pid] -eq $name }
  if (-not $mine) { continue }
  if ($marker) {
    $target = $mine | Where-Object { $_.Title -like ('*' + $marker + '*') } | Select-Object -First 1
  }
  if (-not $target) { $target = $mine | Select-Object -First 1 }
  break
}

if ($target) {
  [HerdrWin]::Raise($target.H) | Out-Null
  if ($env:HERDR_OUT) { [IO.File]::WriteAllText($env:HERDR_OUT, $target.Title) }
}
