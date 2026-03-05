param(
  [ValidateSet("sim", "rtlsdr")]
  [string]$Source = "sim",
  [double]$CenterFreq = 6800000,
  [double]$SampleRate = 2048000,
  [string]$Gain = "auto"
)

$ErrorActionPreference = "Stop"

Write-Host "Starting producer..."
$producerArgs = @(
  "core_producer.py",
  "--source", $Source,
  "--center-freq", $CenterFreq,
  "--sample-rate", $SampleRate,
  "--gain", $Gain
)
Start-Process -FilePath "python" -ArgumentList $producerArgs

Write-Host "Starting websocket gateway..."
Start-Process -FilePath "python" -ArgumentList @("ws_server.py")

Write-Host "Starting client static server on http://127.0.0.1:8080 ..."
Start-Process -FilePath "python" -WorkingDirectory "client" -ArgumentList @("-m", "http.server", "8080")

Write-Host "MVP stack started."
