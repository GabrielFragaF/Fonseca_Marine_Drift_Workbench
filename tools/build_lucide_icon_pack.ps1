param(
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $OutputRoot) {
    $OutputRoot = Join-Path $PSScriptRoot "..\design\icon-system\lucide-gradient"
}

$originalDir = Join-Path $OutputRoot "original"
$brandedDir = Join-Path $OutputRoot "branded"
New-Item -ItemType Directory -Force -Path $originalDir, $brandedDir | Out-Null

$icons = [ordered]@{
    "stranding-data"          = "table-properties"
    "environmental-forcing"  = "waves-arrow-down"
    "simulation-setup"       = "sliders-horizontal"
    "review-run"             = "clipboard-check"
    "results-export"         = "folder-output"
    "netcdf-dataset"         = "file-chart-column"
    "study-area"             = "map-pinned"
    "observation-selection"  = "list-filter-plus"
    "drift-duration"         = "timer"
    "windage"                = "wind"
    "particle-release"       = "git-fork"
    "model-physics"          = "settings"
    "ocean-currents"         = "waves-arrow-up"
    "wind"                   = "wind"
    "waves"                  = "waves-horizontal"
    "bathymetry"             = "layers"
    "sea-surface-temperature" = "thermometer"
    "landmask"               = "map"
    "location"               = "map-pin"
    "date-time"              = "calendar-clock"
    "trajectory"             = "route"
    "particles"              = "circle-dot-dashed"
    "uncertainty"            = "circle-question-mark"
    "validated"              = "shield-check"
    "folder"                 = "folder"
    "search-inspect"         = "search"
    "add"                    = "circle-plus"
    "remove"                 = "circle-minus"
    "run"                    = "circle-play"
    "export"                 = "file-up"
}

$gradient = @"
  <defs>
    <linearGradient id="marine-gradient" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#0F2A44" />
      <stop offset="0.55" stop-color="#287FA3" />
      <stop offset="1" stop-color="#5FC8B5" />
    </linearGradient>
  </defs>
"@

$manifestRows = @()
foreach ($entry in $icons.GetEnumerator()) {
    $semanticName = $entry.Key
    $lucideName = $entry.Value
    $sourceUrl = "https://raw.githubusercontent.com/lucide-icons/lucide/main/icons/$lucideName.svg"
    $originalPath = Join-Path $originalDir "$semanticName.svg"
    $brandedPath = Join-Path $brandedDir "$semanticName.svg"

    $source = (Invoke-WebRequest -Uri $sourceUrl -UseBasicParsing).Content
    [System.IO.File]::WriteAllText($originalPath, $source, [System.Text.UTF8Encoding]::new($false))

    $styled = $source.Replace('stroke="currentColor"', 'stroke="url(#marine-gradient)"')
    $openingTagEnd = $styled.IndexOf('>')
    if ($openingTagEnd -lt 0) {
        throw "Invalid SVG returned for $lucideName"
    }
    $styled = $styled.Insert($openingTagEnd + 1, "`n$gradient")
    $styled = "<!-- Lucide icon: $lucideName. ISC License. -->`n$styled"
    [System.IO.File]::WriteAllText($brandedPath, $styled, [System.Text.UTF8Encoding]::new($false))

    $manifestRows += [pscustomobject]@{
        app_icon = $semanticName
        lucide_icon = $lucideName
        source_url = "https://lucide.dev/icons/$lucideName"
    }
}

$manifestRows | Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $OutputRoot "manifest.csv")

$cards = foreach ($entry in $icons.GetEnumerator()) {
    "<article><img src='./branded/$($entry.Key).svg' alt='$($entry.Key)'><strong>$($entry.Key)</strong><small>Lucide: $($entry.Value)</small></article>"
}

$preview = @"
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Marine Drift Workbench - Lucide gradient icons</title>
  <style>
    :root { --navy:#0f2a44; --ink:#173650; --line:#d8e6eb; --paper:#f4f8f9; }
    * { box-sizing:border-box; }
    body { margin:0; padding:42px; background:linear-gradient(145deg,#edf6f7,#fff 55%,#e9f4f5); color:var(--ink); font-family:"Segoe UI",sans-serif; }
    header { max-width:1280px; margin:0 auto 28px; }
    h1 { margin:0 0 8px; color:var(--navy); font-size:30px; }
    p { margin:0; color:#567080; }
    main { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; max-width:1280px; margin:auto; }
    article { min-height:150px; padding:22px 16px 17px; border:1px solid var(--line); border-radius:16px; background:rgba(255,255,255,.92); box-shadow:0 8px 24px rgba(15,42,68,.07); text-align:center; }
    img { display:block; width:54px; height:54px; margin:0 auto 17px; }
    strong,small { display:block; }
    strong { font-size:13px; }
    small { margin-top:6px; color:#708896; font-size:11px; }
  </style>
</head>
<body>
  <header><h1>Marine Drift Workbench</h1><p>Official Lucide geometry with the marine navy-to-turquoise gradient.</p></header>
  <main>$($cards -join "`n")</main>
</body>
</html>
"@
[System.IO.File]::WriteAllText((Join-Path $OutputRoot "preview.html"), $preview, [System.Text.UTF8Encoding]::new($false))

Write-Output "Created $($icons.Count) original and $($icons.Count) branded SVG files in $OutputRoot"
