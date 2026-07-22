param(
    [string]$PythonPath = "python",
    [string]$TaskName = "Topo AI Agent"
)

$agentCommand = (
    Get-Command topo-agent `
      -ErrorAction Stop
).Source

$action = New-ScheduledTaskAction `
  -Execute $agentCommand `
  -Argument "run"

$trigger = New-ScheduledTaskTrigger `
  -AtStartup

$settings = New-ScheduledTaskSettingsSet `
  -RestartCount 999 `
  -RestartInterval (
    New-TimeSpan -Minutes 1
  ) `
  -ExecutionTimeLimit (
    New-TimeSpan -Days 0
  )

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -RunLevel Highest `
  -Force

Write-Host ("Installed scheduled task: " + $TaskName)