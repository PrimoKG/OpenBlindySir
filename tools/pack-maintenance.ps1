[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('backup','update','rollback')][string]$Action,
    [string]$PackDirectory,
    [string]$BackupDirectory,
    [switch]$ConfirmRollback
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'file-integrity.ps1')
$taskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$taskEnv = Join-Path $taskRoot '.local/docker/hosting.env'

function Invoke-PackDocker([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Docker maintenance failed.' }
}
function Save-PackState {
    $taskBackup = Join-Path $taskRoot ('.local/backups/' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $taskBackup -Force | Out-Null
    $taskAcl = New-Object Security.AccessControl.DirectorySecurity
    $taskOwner = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $taskAcl.SetOwner($taskOwner)
    $taskAcl.SetAccessRuleProtection($true, $false)
    $taskRule = New-Object Security.AccessControl.FileSystemAccessRule($taskOwner, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $taskAcl.AddAccessRule($taskRule)
    Set-Acl -LiteralPath $taskBackup -AclObject $taskAcl
    Invoke-PackDocker @('cp','openblindysir-app-1:/data/state', $taskBackup)
    Copy-Item -LiteralPath $taskEnv -Destination (Join-Path $taskBackup 'hosting.env')
    $taskSources = Join-Path $taskRoot '.local/docker/sources.override.yaml'
    if (Test-Path -LiteralPath $taskSources) { Copy-Item -LiteralPath $taskSources -Destination $taskBackup }
    $taskImages = @{}
    foreach ($service in @('app','bridge','caddy')) {
        $taskImages[$service] = docker inspect "openblindysir-$service-1" --format '{{.Image}}'
        if ($LASTEXITCODE -ne 0) { throw 'Container inspection failed.' }
    }
    $taskMounts = docker inspect openblindysir-app-1 --format '{{json .Mounts}}' | ConvertFrom-Json
    $taskVolume = ($taskMounts | Where-Object Destination -eq '/data').Name
    if ($taskVolume -notmatch '^[a-zA-Z0-9_.-]+$') { throw 'Expected a named data volume.' }
    @{images=$taskImages; volume=$taskVolume} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskBackup 'backup.json') -Encoding UTF8
    $taskHashes = @{}
    foreach ($file in Get-ChildItem -LiteralPath $taskBackup -Recurse -File) {
        $taskRelative = $file.FullName.Substring($taskBackup.Length + 1)
        $taskHashes[$taskRelative] = Get-TaskSha256 $file.FullName
    }
    $taskHashes | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskBackup 'hashes.json') -Encoding UTF8
    Write-Host "Sauvegarde privée / Private backup: $taskBackup"
    return $taskBackup
}

if ($Action -eq 'backup') { [void](Save-PackState); return }
if ($Action -eq 'update') {
    if (-not $PackDirectory) { throw 'Select the verified new pack directory.' }
    $taskNext = (Resolve-Path -LiteralPath $PackDirectory).Path
    if ($taskNext -eq $taskRoot) { throw 'Select a separate new pack.' }
    if (Test-Path -LiteralPath (Join-Path $taskNext '.local/docker/hosting.env')) { throw 'New pack already configured; refusing to overwrite it.' }
    [void](Save-PackState)
    & (Join-Path $taskNext 'tools/load-pack.ps1')
    $taskConfig = Join-Path $taskNext '.local/docker'
    New-Item -ItemType Directory -Path $taskConfig -Force | Out-Null
    Copy-Item -LiteralPath $taskEnv -Destination (Join-Path $taskConfig 'hosting.env')
    $taskSources = Join-Path $taskRoot '.local/docker/sources.override.yaml'
    if (Test-Path -LiteralPath $taskSources) { Copy-Item -LiteralPath $taskSources -Destination $taskConfig }
    & (Join-Path $taskNext 'tools/docker-host.ps1') -Action start -NoBuild -NoBrowser
    Write-Host "Nouvelle installation / New installation: $taskNext"
    return
}
if (-not $ConfirmRollback -or -not $BackupDirectory) { throw 'Rollback replaces session state with the chosen backup. Explicit -ConfirmRollback is required.' }
$taskBackup = (Resolve-Path -LiteralPath $BackupDirectory).Path
$taskHashes = Get-Content -Raw -LiteralPath (Join-Path $taskBackup 'hashes.json') | ConvertFrom-Json
foreach ($item in $taskHashes.PSObject.Properties) {
    $taskFile = [IO.Path]::GetFullPath((Join-Path $taskBackup $item.Name))
    if (-not $taskFile.StartsWith($taskBackup + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid backup path.' }
    if ((Get-TaskSha256 $taskFile) -ne $item.Value) { throw 'Backup integrity check failed.' }
}
$taskRecord = Get-Content -Raw -LiteralPath (Join-Path $taskBackup 'backup.json') | ConvertFrom-Json
if ($taskRecord.volume -notmatch '^[a-zA-Z0-9_.-]+$') { throw 'Invalid volume.' }
$taskCurrentMounts = docker inspect openblindysir-app-1 --format '{{json .Mounts}}' | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $taskRecord.volume -ne ($taskCurrentMounts | Where-Object Destination -eq '/data').Name) { throw 'Backup volume does not match this installation.' }
foreach ($item in $taskRecord.images.PSObject.Properties) {
    if ($item.Value -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Invalid image identity.' }
    Invoke-PackDocker @('image','inspect','--format','{{.Id}}',$item.Value)
}
[void](Save-PackState)
& (Join-Path $taskRoot 'tools/docker-host.ps1') -Action stop -NoBuild -NoBrowser
Invoke-PackDocker @('run','--rm','--network','none','--read-only','--cap-drop','ALL',
    '--mount',"type=volume,source=$($taskRecord.volume),target=/data",
    '--mount',"type=bind,source=$taskBackup/state,target=/restore,readonly",'--entrypoint','python',$taskRecord.images.app,
    '-c','import shutil; shutil.copytree("/restore", "/data/state", dirs_exist_ok=True)')
Copy-Item -LiteralPath (Join-Path $taskBackup 'hosting.env') -Destination $taskEnv
$taskSources = Join-Path $taskRoot '.local/docker/sources.override.yaml'
$taskSavedSources = Join-Path $taskBackup 'sources.override.yaml'
if (Test-Path -LiteralPath $taskSavedSources) {
    Copy-Item -LiteralPath $taskSavedSources -Destination $taskSources
} elseif (Test-Path -LiteralPath $taskSources) {
    # Preserve the later configuration privately, but stop applying it to the restored pack.
    $taskResolvedSources = [IO.Path]::GetFullPath($taskSources)
    if (-not $taskResolvedSources.StartsWith($taskRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid installation path.' }
    Move-Item -LiteralPath $taskResolvedSources -Destination ($taskResolvedSources + '.before-rollback-' + [Guid]::NewGuid().ToString('N'))
}
$taskOverride = Join-Path $taskRoot '.local/docker/rollback.override.yaml'
@("services:","  app:","    image: $($taskRecord.images.app)","  bridge:","    image: $($taskRecord.images.bridge)","  caddy:","    image: $($taskRecord.images.caddy)") | Set-Content -LiteralPath $taskOverride -Encoding UTF8
$taskCompose = @('compose','--env-file',$taskEnv,'-f',(Join-Path $taskRoot 'compose.yaml'))
if (Select-String -LiteralPath $taskEnv -Pattern '^CADDY_PROFILE=public$' -Quiet) { $taskCompose += @('-f',(Join-Path $taskRoot 'deploy/compose.public.yaml')) }
if (Test-Path -LiteralPath $taskSources) { $taskCompose += @('-f',$taskSources) }
$taskCompose += @('-f',$taskOverride,'up','-d','--no-build','--wait','--wait-timeout','120')
Invoke-PackDocker $taskCompose
Write-Host 'État et images restaurés / State and images restored. Keep the rollback override until the next planned update.'
