param(
    [string]$TileUrl = "https://download.geofabrik.de/asia/india/southern-zone-shortbread-1.0.mbtiles",
    [string]$Output = "map_data\tiles\india-southern-zone-shortbread.mbtiles"
)

$ErrorActionPreference = "Stop"
$outputPath = Join-Path (Get-Location) $Output
$outputDir = Split-Path -Parent $outputPath

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

Write-Host "Downloading OSM vector tiles..."
Write-Host $TileUrl
Write-Host "-> $outputPath"

Invoke-WebRequest -Uri $TileUrl -OutFile $outputPath

Write-Host "Done. Start the backend and open /api/maps/tilejson.json to verify."
