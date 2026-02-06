$ErrorActionPreference = "Stop"

$base = $env:BASE_URL
$avatar = $env:AVATAR_FILE
$ref = $env:REF_VIDEO_FILE

if (-not $base) {
  Write-Host "Set BASE_URL, e.g. https://your-host"
  exit 1
}
if (-not $avatar -or -not (Test-Path $avatar)) {
  Write-Host "Set AVATAR_FILE to a valid image path"
  exit 1
}
if (-not $ref -or -not (Test-Path $ref)) {
  Write-Host "Set REF_VIDEO_FILE to a valid video path"
  exit 1
}

Write-Host "Creating ApolloAvatar task..."
$create = curl -sS -X POST "$base/api/apollo/avatar/tasks" `
  -F "avatar_file=@$avatar" `
  -F "ref_video_file=@$ref" `
  -F "duration_sec=15" `
  -F "prompt=demo" `
  -F "live_enabled=false"

$taskId = (ConvertFrom-Json $create).task_id
if (-not $taskId) {
  Write-Host "Failed to create task: $create"
  exit 1
}
Write-Host "Task: $taskId"

Write-Host "Trigger generate..."
curl -sS -X POST "$base/api/apollo/avatar/$taskId/generate" `
  -H "Content-Type: application/json" `
  -d "{}" | Out-Null

Write-Host "Polling status..."
for ($i = 0; $i -lt 60; $i++) {
  Start-Sleep -Seconds 2
  $status = curl -sS "$base/api/tasks/$taskId"
  $obj = ConvertFrom-Json $status
  Write-Host "pack_status=$($obj.pack_status) subtitles_status=$($obj.subtitles_status) dub_status=$($obj.dub_status)"
  if ($obj.pack_status -eq "done") { break }
}

Write-Host "Checking pack endpoint (expect 200 when ready, 409 before ready)..."
curl -sS -o $null -w "%{http_code}`n" "$base/v1/tasks/$taskId/pack"
