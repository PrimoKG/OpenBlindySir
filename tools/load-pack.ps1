[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'file-integrity.ps1')
$taskPack = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
foreach ($line in Get-Content -LiteralPath (Join-Path $taskPack 'SHA256SUMS')) {
    if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { throw 'Invalid checksum manifest.' }
    $taskExpected = $Matches[1]
    $taskFile = [IO.Path]::GetFullPath((Join-Path $taskPack $Matches[2]))
    if (-not $taskFile.StartsWith($taskPack + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid pack path.' }
    if ((Get-TaskSha256 $taskFile) -ne $taskExpected) { throw "Integrity check failed: $taskFile" }
}
docker load --input (Join-Path $taskPack 'images.tar')
if ($LASTEXITCODE -ne 0) { throw 'Docker load failed.' }
$taskManifest = Get-Content -Raw -LiteralPath (Join-Path $taskPack 'manifest.json') | ConvertFrom-Json
foreach ($item in $taskManifest.images.PSObject.Properties) {
    $taskId = docker image inspect --format '{{.Id}}' $item.Value.reference
    if ($LASTEXITCODE -ne 0 -or $taskId -ne $item.Value.id) { throw 'Loaded image identity mismatch.' }
}
docker tag $taskManifest.wizard_alias openblindysir-server:local
if ($LASTEXITCODE -ne 0) { throw 'Wizard alias failed.' }
Write-Host 'Pack verified and loaded. Start: .\tools\party-assistant.ps1'
