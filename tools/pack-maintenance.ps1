[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('backup','update','rollback')][string]$Action,
    [string]$PackDirectory,
    [string]$BackupDirectory,
    [switch]$ConfirmRollback
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'file-integrity.ps1')
. (Join-Path $PSScriptRoot 'private-config.ps1')
$taskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$taskEnv = Join-Path $taskRoot '.local/docker/hosting.env'
if ($Action -ne 'backup' -and $taskRoot.Contains(',')) { throw 'Use an installation directory without commas for offline volume restoration.' }

function Invoke-PackDocker([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Docker maintenance failed.' }
}
function Save-PackState {
    $taskBackup = Join-Path $taskRoot ('.local/backups/' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N'))
    Assert-TaskUnlinkedPath $taskEnv
    New-TaskPrivateDirectory $taskBackup
    $taskImages = @{}
    $taskRunning = @{}
    foreach ($service in @('app','bridge','caddy')) {
        $taskImages[$service] = docker inspect "openblindysir-$service-1" --format '{{.Image}}'
        if ($LASTEXITCODE -ne 0) { throw 'Container inspection failed.' }
        $taskRunning[$service] = (docker inspect "openblindysir-$service-1" --format '{{.State.Running}}') -eq 'true'
        if ($LASTEXITCODE -ne 0) { throw 'Container inspection failed.' }
    }
    $taskMounts = docker inspect openblindysir-app-1 --format '{{json .Mounts}}' | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Container inspection failed.' }
    $taskVolume = ($taskMounts | Where-Object Destination -eq '/data').Name
    if ($taskVolume -notmatch '^[a-zA-Z0-9_.-]+$') { throw 'Expected a named data volume.' }
    $taskBridgeMounts = docker inspect openblindysir-bridge-1 --format '{{json .Mounts}}' | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Container inspection failed.' }
    $taskBridgeVolume = ($taskBridgeMounts | Where-Object Destination -eq '/data').Name
    if ($taskBridgeVolume -notmatch '^[a-zA-Z0-9_.-]+$') { throw 'Expected a named Bridge volume.' }
    # Graceful shutdown flushes the final snapshot and gives the copy one stable point in time.
    # Restart only services that were running, including after a copy/stop failure.
    try {
        foreach ($service in @('bridge','caddy','app')) {
            if ($taskRunning[$service]) { Invoke-PackDocker @('stop','--time','20',"openblindysir-$service-1") | Out-Null }
        }
        Invoke-PackDocker @('cp','openblindysir-app-1:/data/state', $taskBackup)
        Invoke-PackDocker @('cp','openblindysir-bridge-1:/data/config.toml', (Join-Path $taskBackup 'bridge-config.toml'))
        Copy-Item -LiteralPath $taskEnv -Destination (Join-Path $taskBackup 'hosting.env')
        $taskSources = Join-Path $taskRoot '.local/docker/sources.override.yaml'
        if (Test-Path -LiteralPath $taskSources) {
            Assert-TaskUnlinkedPath $taskSources
            Copy-Item -LiteralPath $taskSources -Destination $taskBackup
        }
    } finally {
        $taskRestartFailed = $false
        foreach ($service in @('app','caddy','bridge')) {
            if ($taskRunning[$service]) {
                try { Invoke-PackDocker @('start',"openblindysir-$service-1") | Out-Null }
                catch { $taskRestartFailed = $true }
            }
        }
        if ($taskRestartFailed) { throw 'Backup could not restart all previously running services. Use Start / Status.' }
    }
    @{format=2; images=$taskImages; volume=$taskVolume; bridge_volume=$taskBridgeVolume} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskBackup 'backup.json') -Encoding UTF8
    $taskHashes = @{}
    foreach ($file in Get-ChildItem -LiteralPath $taskBackup -Recurse -File) {
        $taskRelative = $file.FullName.Substring($taskBackup.Length + 1).Replace('\', '/')
        $taskHashes[$taskRelative] = Get-TaskSha256 $file.FullName
    }
    $taskHashes | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskBackup 'hashes.json') -Encoding UTF8
    Write-Host "Sauvegarde privée / Private backup: $taskBackup"
    return $taskBackup
}

function Restore-PackData([string]$Backup, $Record) {
    foreach ($taskRestore in @(@($Record.volume,'state','/restore','--directory','/data/state'), @($Record.bridge_volume,'bridge-config.toml','/restore.toml','--file','/data/config.toml'))) {
        Invoke-PackDocker @('run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
            '--mount',"type=volume,source=$($taskRestore[0]),target=/data",
            '--mount',"type=bind,source=$Backup/$($taskRestore[1]),target=$($taskRestore[2]),readonly",
            '--mount',"type=bind,source=$taskRoot/tools/restore_pack_state.py,target=/restore-tool.py,readonly",'--entrypoint','python',$Record.images.app,
            '/restore-tool.py',$taskRestore[3],$taskRestore[2],$taskRestore[4]) | Out-Null
    }
}

function Start-PackRecord([string]$Backup, $Record) {
    $taskConfig = Join-Path $taskRoot '.local/docker'
    New-TaskPrivateDirectory $taskConfig
    Copy-Item -LiteralPath (Join-Path $Backup 'hosting.env') -Destination $taskEnv
    Protect-TaskPath $taskEnv
    $taskSources = Join-Path $taskConfig 'sources.override.yaml'
    $taskSavedSources = Join-Path $Backup 'sources.override.yaml'
    if (Test-Path -LiteralPath $taskSavedSources) {
        Copy-Item -LiteralPath $taskSavedSources -Destination $taskSources
        Protect-TaskPath $taskSources
    } elseif (Test-Path -LiteralPath $taskSources) {
        Assert-TaskUnlinkedPath $taskSources
        Move-Item -LiteralPath $taskSources -Destination ($taskSources + '.before-rollback-' + [Guid]::NewGuid().ToString('N'))
    }
    $taskOverride = Join-Path $taskConfig 'rollback.override.yaml'
    Assert-TaskUnlinkedPath $taskOverride
    @('services:',"  app:","    image: $($Record.images.app)","  bridge:","    image: $($Record.images.bridge)","  caddy:","    image: $($Record.images.caddy)") | Set-Content -LiteralPath $taskOverride -Encoding UTF8
    Protect-TaskPath $taskOverride
    & (Join-Path $taskRoot 'tools/docker-host.ps1') -Action start -NoBuild -NoBrowser
}

if ($Action -eq 'backup') { [void](Save-PackState); return }
if ($Action -eq 'update') {
    if (-not $PackDirectory) { throw 'Select the verified new pack directory.' }
    $taskNext = (Resolve-Path -LiteralPath $PackDirectory).Path
    if ($taskNext -eq $taskRoot) { throw 'Select a separate new pack.' }
    if (Test-Path -LiteralPath (Join-Path $taskNext '.local/docker/hosting.env')) { throw 'New pack already configured; refusing to overwrite it.' }
    & (Join-Path $taskNext 'tools/load-pack.ps1')
    $taskConfig = Join-Path $taskNext '.local/docker'
    New-TaskPrivateDirectory $taskConfig
    Copy-Item -LiteralPath $taskEnv -Destination (Join-Path $taskConfig 'hosting.env')
    Protect-TaskPath (Join-Path $taskConfig 'hosting.env')
    $taskSources = Join-Path $taskRoot '.local/docker/sources.override.yaml'
    if (Test-Path -LiteralPath $taskSources) {
        Assert-TaskUnlinkedPath $taskSources
        Copy-Item -LiteralPath $taskSources -Destination $taskConfig
        Protect-TaskPath (Join-Path $taskConfig 'sources.override.yaml')
    }
    $taskSafetyBackup = Save-PackState
    $taskSafetyRecord = Get-Content -Raw -LiteralPath (Join-Path $taskSafetyBackup 'backup.json') | ConvertFrom-Json
    try {
        & (Join-Path $taskNext 'tools/docker-host.ps1') -Action start -NoBuild -NoBrowser
    } catch {
        $taskFailure = $_
        try {
            & (Join-Path $taskNext 'tools/docker-host.ps1') -Action stop -NoBuild -NoBrowser
            Restore-PackData $taskSafetyBackup $taskSafetyRecord
            Start-PackRecord $taskSafetyBackup $taskSafetyRecord
        } catch { throw "Update failed and recovery failed. Keep private backup $taskSafetyBackup. Use Status. $($_.Exception.Message)" }
        throw "Update failed; the previous state, Bridge and images were restored. $($taskFailure.Exception.Message)"
    }
    Write-Host "Nouvelle installation / New installation: $taskNext"
    return
}
if (-not $ConfirmRollback -or -not $BackupDirectory) { throw 'Rollback replaces session state with the chosen backup. Explicit -ConfirmRollback is required.' }
$taskBackup = (Resolve-Path -LiteralPath $BackupDirectory).Path
Assert-TaskUnlinkedPath $taskBackup
if ($taskBackup.Contains(',')) { throw 'Use a backup directory without commas for offline volume restoration.' }
$taskHashes = Get-Content -Raw -LiteralPath (Join-Path $taskBackup 'hashes.json') | ConvertFrom-Json
foreach ($taskRequired in @('backup.json','hosting.env','state/session.json','bridge-config.toml')) {
    if (-not $taskHashes.PSObject.Properties[$taskRequired]) { throw 'Incomplete backup. Use a format 2 maintenance backup.' }
}
foreach ($item in $taskHashes.PSObject.Properties) {
    $taskFile = [IO.Path]::GetFullPath((Join-Path $taskBackup $item.Name))
    if (-not $taskFile.StartsWith($taskBackup + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid backup path.' }
    Assert-TaskUnlinkedPath $taskFile
    if ((Get-TaskSha256 $taskFile) -ne $item.Value) { throw 'Backup integrity check failed.' }
}
$taskRecord = Get-Content -Raw -LiteralPath (Join-Path $taskBackup 'backup.json') | ConvertFrom-Json
$taskServices = ($taskRecord.images.PSObject.Properties.Name | Sort-Object) -join ','
if ($taskRecord.format -ne 2 -or $taskServices -ne 'app,bridge,caddy') { throw 'Unsupported or incomplete backup.' }
if ($taskRecord.volume -notmatch '^[a-zA-Z0-9_.-]+$') { throw 'Invalid volume.' }
if ($taskRecord.bridge_volume -notmatch '^[a-zA-Z0-9_.-]+$') { throw 'Invalid Bridge volume.' }
$taskCurrentMounts = docker inspect openblindysir-app-1 --format '{{json .Mounts}}' | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $taskRecord.volume -ne ($taskCurrentMounts | Where-Object Destination -eq '/data').Name) { throw 'Backup volume does not match this installation.' }
$taskCurrentBridgeMounts = docker inspect openblindysir-bridge-1 --format '{{json .Mounts}}' | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $taskRecord.bridge_volume -ne ($taskCurrentBridgeMounts | Where-Object Destination -eq '/data').Name) { throw 'Backup Bridge volume does not match this installation.' }
foreach ($item in $taskRecord.images.PSObject.Properties) {
    if ($item.Value -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Invalid image identity.' }
    Invoke-PackDocker @('image','inspect','--format','{{.Id}}',$item.Value)
}
$taskSafetyBackup = Save-PackState
$taskSafetyRecord = Get-Content -Raw -LiteralPath (Join-Path $taskSafetyBackup 'backup.json') | ConvertFrom-Json
try {
    & (Join-Path $taskRoot 'tools/docker-host.ps1') -Action stop -NoBuild -NoBrowser
    Restore-PackData $taskBackup $taskRecord
    Start-PackRecord $taskBackup $taskRecord
} catch {
    $taskFailure = $_
    try {
        & (Join-Path $taskRoot 'tools/docker-host.ps1') -Action stop -NoBuild -NoBrowser
        Restore-PackData $taskSafetyBackup $taskSafetyRecord
        Start-PackRecord $taskSafetyBackup $taskSafetyRecord
    } catch { throw "Rollback failed and recovery failed. Keep private backup $taskSafetyBackup. Use Status. $($_.Exception.Message)" }
    throw "Rollback failed; the state from before this attempt was restored. $($taskFailure.Exception.Message)"
}
Write-Host 'État et images restaurés / State and images restored. Keep the rollback override until the next planned update.'
