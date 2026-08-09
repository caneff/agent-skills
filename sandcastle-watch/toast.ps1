param([string]$Title, [string]$Body)
# Build the toast XML as a string and type-load XmlDocument explicitly: WinRT
# nodes throw on GetElementsByTagName indexing, and the manager load does not
# imply the XML one.
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType=WindowsRuntime] > $null
# Text is log-derived, so it carries both markup chars and the ANSI colour
# sequences sandcastle wraps its ✓/✗ markers in. LoadXml throws on a bare & and
# again on ESC, so escape the five entities, then drop the C0 controls XML 1.0
# forbids (tab/LF/CR stay).
function Clean([string]$s) {
  [System.Security.SecurityElement]::Escape($s) -replace '[\x00-\x08\x0B\x0C\x0E-\x1F]', ''
}
$xml = [Windows.Data.Xml.Dom.XmlDocument]::new()
$xml.LoadXml("<toast><visual><binding template='ToastText02'><text id='1'>$(Clean $Title)</text><text id='2'>$(Clean $Body)</text></binding></visual></toast>")
# ponytail: borrows PowerShell's AUMID, so Action Center attributes the toast to
# "Windows PowerShell". A custom "Sandcastle" identity needs a registry write.
$aumid = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($aumid).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
