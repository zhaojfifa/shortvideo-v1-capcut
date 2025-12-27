$ErrorActionPreference="Stop"
$base="http://127.0.0.1:8000"
$tid="smokedub123"

Write-Host "1) GET task"
curl.exe -sS "$base/api/tasks/$tid" | Out-Host

Write-Host "2) GET pack (headers)"
curl.exe -sS -D - "$base/v1/tasks/$tid/pack" -o NUL | Out-Host

Write-Host "3) Download pack"
curl.exe -L -o "${tid}_capcut_pack.zip" "$base/v1/tasks/$tid/pack" | Out-Host
Get-Item ".\${tid}_capcut_pack.zip" | Select FullName,Length | Out-Host

Write-Host "OK"
