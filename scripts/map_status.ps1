$tilePath = Join-Path (Get-Location) "map_data\tiles\india-southern-zone-shortbread.mbtiles"
$graphPath = Join-Path (Get-Location) "map_data\graphs\india-southern-zone"

Write-Host "Vector tiles:"
if (Test-Path $tilePath) {
    $item = Get-Item $tilePath
    Write-Host "  READY $($item.FullName) $([math]::Round($item.Length / 1MB, 2)) MB"
} else {
    Write-Host "  MISSING $tilePath"
}

Write-Host "Routing graph:"
if (Test-Path $graphPath) {
    Write-Host "  READY $graphPath"
} else {
    Write-Host "  MISSING $graphPath"
}
