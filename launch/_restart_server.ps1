# Restart DevBIM server detached via WMI (ASCII only: PowerShell reads ps1 as cp1251).
# Script lives in launch\, project root is one level up.
$proj = Split-Path -Parent $PSScriptRoot
$conns = Get-NetTCPConnection -LocalPort 9090 -State Listen -ErrorAction SilentlyContinue
foreach ($c in $conns) {
  try { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue } catch {}
}
Start-Sleep 2
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
  CommandLine = 'cmd /c cd /d "' + $proj + '" && launch\_ir_server_hidden.bat'
}
Write-Output ("restart: pid=" + $r.ProcessId + " ret=" + $r.ReturnValue)
