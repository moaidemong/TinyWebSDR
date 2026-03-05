param(
  [string]$Timezone = "Asia/Seoul",
  [string]$StateFile = "runtime/band_state.json"
)

$ErrorActionPreference = "Stop"

Write-Host "Starting scheduler..."
Start-Process -FilePath "python" -ArgumentList @(
  "scheduler.py",
  "--timezone", $Timezone,
  "--state-file", $StateFile
)

Write-Host "Starting websocket gateway..."
Start-Process -FilePath "python" -ArgumentList @(
  "ws_server.py",
  "--state-file", $StateFile
)

Write-Host "Starting client static server on http://127.0.0.1:8080 ..."
Start-Process -FilePath "python" -WorkingDirectory "client" -ArgumentList @("-m", "http.server", "8080")

Write-Host "Title stream stack started."
