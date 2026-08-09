[CmdletBinding(DefaultParameterSetName = 'Text')]
param(
  [string]$Title,
  # -Body is for literals the caller wrote. Log-derived text goes through
  # -BodyFile, which never crosses a shell, so a milestone carrying $(...) or
  # backticks cannot execute on the way here. Parameter sets make passing both
  # an error rather than a silent precedence rule.
  [Parameter(ParameterSetName = 'Text')][string]$Body,
  [Parameter(ParameterSetName = 'File', Mandatory)][string]$BodyFile
)
if ($BodyFile) {
  if (-not (Test-Path -LiteralPath $BodyFile)) {
    # ponytail: warn and exit 0. The watch loop calls this every milestone and
    # must not die because a toast had nothing to say.
    Write-Warning "toast: no body file at $BodyFile"
    exit 0
  }
  # -Encoding UTF8 or 5.1 decodes the ✓/✗ markers as the ANSI codepage. -Raw
  # returns $null on an empty file, so coalesce before trimming. TrimEnd, not
  # Trim: sandcastle indents its "  ✓ id" markers and that indent is meaningful.
  $raw = Get-Content -LiteralPath $BodyFile -Raw -Encoding UTF8
  if ($null -eq $raw) { $raw = '' }
  $Body = $raw.TrimEnd()
}
# Build the toast XML as a string and type-load XmlDocument explicitly: WinRT
# nodes throw on GetElementsByTagName indexing, and the manager load does not
# imply the XML one.
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType=WindowsRuntime] > $null
# LoadXml throws on a bare & and again on the ESC of an ANSI colour sequence, so
# escape the five entities, then drop the C0 controls XML 1.0 forbids.
function Clean([string]$s) {
  [System.Security.SecurityElement]::Escape($s) -replace '[\x00-\x08\x0B\x0C\x0E-\x1F]', ''
}
$xml = [Windows.Data.Xml.Dom.XmlDocument]::new()
$xml.LoadXml("<toast><visual><binding template='ToastText02'><text id='1'>$(Clean $Title)</text><text id='2'>$(Clean $Body)</text></binding></visual></toast>")
# ponytail: borrows PowerShell's AUMID, so Action Center attributes the toast to
# "Windows PowerShell". A custom "Sandcastle" identity needs a registry write.
$aumid = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($aumid).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
