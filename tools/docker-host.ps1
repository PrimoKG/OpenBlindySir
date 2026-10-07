[CmdletBinding()]
param(
    [ValidateSet('init', 'start', 'stop', 'status', 'open', 'certificate', 'bridge-credential', 'bridge-revoke')]
    [string]$Action = 'start',
    [string]$Address,
    [ValidateSet('private', 'public')][string]$Mode = 'private',
    [string]$MusicDir,
    [string]$BridgeId,
    [string]$BridgeName = 'Bridge',
    [string]$CredentialOutput,
    [switch]$Demo,
    [switch]$NoBrowser,
    [switch]$NoBuild
)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$taskData = Join-Path $taskRoot '.local/docker'
$taskEnv = Join-Path $taskData 'hosting.env'
. (Join-Path $PSScriptRoot 'docker-context.ps1')
. (Join-Path $PSScriptRoot 'file-integrity.ps1')

function Build-DockerImages([string[]]$Targets) {
    $taskContext = New-DockerBuildContext $taskRoot $taskData
    try {
        foreach ($target in $Targets) {
            $tag = switch ($target) { 'app' { 'openblindysir-server:local' } 'bridge' { 'openblindysir-bridge:local' } 'proxy' { 'openblindysir-caddy:local' } default { throw 'Unknown image target.' } }
            Invoke-Docker @('build', '--target', $target, '--tag', $tag, $taskContext)
        }
    } finally { Remove-DockerBuildContext $taskContext $taskData }
}

function Invoke-Docker([string[]]$DockerArguments) {
    & docker @DockerArguments
    if ($LASTEXITCODE -ne 0) { throw "Docker a échoué (code $LASTEXITCODE)." }
}

function Open-HostBrowser([string]$Url) {
    try { Start-Process $Url }
    catch { Write-Warning "Ouvrez votre navigateur : $Url" }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Installez Docker Desktop avec Compose, puis démarrez le moteur Linux.'
}
# Configuration belongs to this launcher, independent of variables from native hosting.
$taskKeys = @('DOMAIN', 'TLS_HOST', 'HTTPS_PORT', 'BIND_IP', 'CADDY_PROFILE',
    'MUSIC_DIR', 'BRIDGE_DEMO', 'BRIDGE_ALLOW_FULL_REVIEW', 'BLIND_PASSWORD', 'HOST_PASSWORD', 'BRIDGE_SECRET', 'BRIDGE_SECRETS',
    'COMPOSE_FILE', 'COMPOSE_PROFILES', 'COMPOSE_PROJECT_NAME')
$taskSaved = @{}
foreach ($key in $taskKeys) {
    $taskSaved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
    Remove-Item -LiteralPath "Env:$key" -ErrorAction SilentlyContinue
}
Push-Location $taskRoot
try {
    if ($Action -eq 'init') {
        if (Test-Path -LiteralPath $taskEnv) { throw 'Configuration existante : modifiez .local/docker/hosting.env.' }
        if (-not $Address) { throw 'Indiquez -Address (IP LAN/VPN:port ou domaine public).' }
        New-Item -ItemType Directory -Path $taskData -Force | Out-Null
        if ($Demo) {
            $MusicDir = Join-Path $taskData 'demo-mount'
            New-Item -ItemType Directory -Path $MusicDir -Force | Out-Null
        }
        if (-not $MusicDir -or -not (Test-Path -LiteralPath $MusicDir -PathType Container)) {
            throw 'Indiquez -MusicDir avec un dossier existant, ou utilisez -Demo.'
        }
        $taskMusic = (Resolve-Path -LiteralPath $MusicDir).Path.Replace('\', '/')
        if (-not $NoBuild) { Build-DockerImages @('app') }
        $taskUser = '0:0'
        if ([Environment]::OSVersion.Platform -eq 'Unix') { $taskUser = "$(id -u):$(id -g)" }
        $taskInit = @('run', '--rm', '--user', $taskUser, '--mount',
            "type=bind,source=$taskData,target=/setup", 'openblindysir-server:local',
            'python', '/opt/tools/docker_config.py', '--address', $Address,
            '--mode', $Mode, '--music-dir', $taskMusic)
        if ($Demo) { $taskInit += '--demo' }
        Invoke-Docker $taskInit
        Write-Host 'Prêt : lancez .\tools\docker-host.ps1 start.'
        return
    }
    if (-not (Test-Path -LiteralPath $taskEnv)) {
        throw 'Configuration absente : utilisez init -Address ... -MusicDir ... (ou -Demo).'
    }
    # Read only public routing metadata; never print the configuration or secrets.
    $taskRouting = @{}
    foreach ($line in [IO.File]::ReadAllLines($taskEnv)) {
        if ($line -match '^(DOMAIN|CADDY_PROFILE)=(.+)$') { $taskRouting[$Matches[1]] = $Matches[2] }
    }
    $taskUrl = 'https://' + $taskRouting['DOMAIN'] + '/host'
    $taskCompose = @('compose', '--env-file', $taskEnv, '-f', (Join-Path $taskRoot 'compose.yaml'))
    if ($taskRouting['CADDY_PROFILE'] -eq 'public') {
        $taskCompose += @('-f', (Join-Path $taskRoot 'deploy/compose.public.yaml'))
    } elseif ($taskRouting['CADDY_PROFILE'] -ne 'private') { throw 'CADDY_PROFILE doit être private ou public.' }
    # Keep user music mounts when rebuilding or recreating the deployment.
    $taskSourcesOverride = Join-Path $taskData 'sources.override.yaml'
    if (Test-Path -LiteralPath $taskSourcesOverride -PathType Leaf) {
        $taskCompose += @('-f', $taskSourcesOverride)
    }
    $taskRollback = Join-Path $taskData 'rollback.override.yaml'
    if (Test-Path -LiteralPath $taskRollback -PathType Leaf) { $taskCompose += @('-f', $taskRollback) }
    switch ($Action) {
        'start' {
            if (-not $NoBuild) { Build-DockerImages @('app', 'bridge', 'proxy') }
            $taskUp = @('up', '-d', '--no-build', '--wait', '--wait-timeout', '120')
            Invoke-Docker ($taskCompose + $taskUp)
            Write-Host "Partie : https://$($taskRouting['DOMAIN'])`nHôte : $taskUrl"
            if ($taskRouting['CADDY_PROFILE'] -eq 'private') {
                Invoke-Docker ($taskCompose + @('cp', 'caddy:/data/caddy/pki/authorities/local/root.crt',
                    (Join-Path $taskData 'root.crt')))
                Write-Host "Certificat à approuver sur les appareils : $(Join-Path $taskData 'root.crt')"
                Write-Host "SHA256 du fichier : $(Get-TaskSha256 (Join-Path $taskData 'root.crt'))"
                Write-Host 'Guide FR / EN : docs/certificat-local.md / docs/local-certificate.en.md'
            }
            if (-not $NoBrowser) { Open-HostBrowser $taskUrl }
        }
        'stop' { Invoke-Docker ($taskCompose + @('down')) }
        'status' { Invoke-Docker ($taskCompose + @('ps')) }
        'bridge-credential' {
            if (-not $BridgeId -or -not $CredentialOutput) {
                throw 'Indiquez -BridgeId UUID et -CredentialOutput /data/state/issued-NOM.toml (nouveau fichier privé dans le conteneur).'
            }
            Invoke-Docker ($taskCompose + @('exec', '-T', 'app', 'python', '-m',
                'openblindysir_server', 'bridge-credential', '--bridge-id', $BridgeId,
                '--name', $BridgeName, '--output', $CredentialOutput))
            Write-Host 'Transférez le fichier privé au propriétaire de ce Bridge. Voir docs/v0.5.md.'
        }
        'bridge-revoke' {
            if (-not $BridgeId) { throw 'Indiquez -BridgeId UUID.' }
            Invoke-Docker ($taskCompose + @('exec', '-T', 'app', 'python', '-m',
                'openblindysir_server', 'bridge-revoke', '--bridge-id', $BridgeId))
        }
        'open' { Open-HostBrowser $taskUrl }
        'certificate' {
            if ($taskRouting['CADDY_PROFILE'] -ne 'private') { throw 'Le mode public utilise un certificat public.' }
            Invoke-Docker ($taskCompose + @('cp', 'caddy:/data/caddy/pki/authorities/local/root.crt',
                (Join-Path $taskData 'root.crt')))
            Write-Host "Certificat : $(Join-Path $taskData 'root.crt')"
            Write-Host "SHA256 du fichier : $(Get-TaskSha256 (Join-Path $taskData 'root.crt'))"
            Write-Host 'Guide FR / EN : docs/certificat-local.md / docs/local-certificate.en.md'
        }
    }
} finally {
    Pop-Location
    foreach ($key in $taskKeys) {
        if ($null -eq $taskSaved[$key]) { Remove-Item -LiteralPath "Env:$key" -ErrorAction SilentlyContinue }
        else { Set-Item -LiteralPath "Env:$key" -Value $taskSaved[$key] }
    }
}
