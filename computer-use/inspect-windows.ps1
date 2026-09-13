Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::IsControlElementProperty, $true)
$windows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
Write-Output "count=$($windows.Count)"
foreach ($w in $windows) {
  $name = $w.Current.Name
  $cls = $w.Current.ClassName
  if ($name) { Write-Output "$name | $cls" }
}
