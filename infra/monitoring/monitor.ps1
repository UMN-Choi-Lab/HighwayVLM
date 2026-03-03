param(
    [ValidateSet("summary", "hourly", "incidents", "watch")]
    [string]$Mode = "summary",
    [string]$CameraId = "",
    [int]$Limit = 20,
    [int]$Interval = 60,
    [switch]$Json
)

$args = @("infra/monitoring/monitor.py", $Mode)

if ($CameraId) {
    $args += @("--camera-id", $CameraId)
}

if ($Mode -in @("hourly", "incidents", "watch")) {
    $args += @("--limit", $Limit.ToString())
}

if ($Mode -eq "watch") {
    $args += @("--interval", $Interval.ToString())
}

if ($Json -and $Mode -in @("hourly", "incidents")) {
    $args += "--json"
}

python @args
