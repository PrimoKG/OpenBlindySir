[CmdletBinding()]
param(
    [ValidateSet('init', 'start', 'stop', 'status', 'open', 'certificate')]
    [string]$Action = 'start',
    [string]$Address,
    [ValidateSet('private', 'public')][string]$Mode = 'private',
    [string]$MusicDir,
    [switch]$Demo,
    [switch]$NoBrowser,
    [switch]$NoBuild
)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$taskData = Join-Path $taskRoot '.local/docker'
$taskEnv = Join-Path $taskData 'hosting.env'

function Invoke-Docker([string[]]$DockerArguments) {
    & docker @DockerArguments
    if ($LASTEXITCODE -ne 0) { throw "Docker a échoué (code $LASTEXITCODE)." }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Installez Docker Desktop avec Compose, puis démarrez le moteur Linux.'
}
# Configuration belongs to this launcher, independent of variables from native hosting.
$taskKeys = @('DOMAIN', 'TLS_HOST', 'HTTPS_PORT', 'BIND_IP', 'CADDY_PROFILE',
    'MUSIC_DIR', 'BRIDGE_DEMO', 'BLIND_PASSWORD', 'HOST_PASSWORD', 'BRIDGE_SECRET',
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
        if (-not $NoBuild) { Invoke-Docker @('build', '--target', 'app', '--tag', 'openblindysir-server:local', '.') }
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
    switch ($Action) {
        'start' {
            $taskUp = @('up', '-d', '--wait', '--wait-timeout', '120')
            if (-not $NoBuild) { $taskUp += '--build' }
            Invoke-Docker ($taskCompose + $taskUp)
            Write-Host "Partie : https://$($taskRouting['DOMAIN'])`nHôte : $taskUrl"
            if ($taskRouting['CADDY_PROFILE'] -eq 'private') {
                Invoke-Docker ($taskCompose + @('cp', 'caddy:/data/caddy/pki/authorities/local/root.crt',
                    (Join-Path $taskData 'root.crt')))
                Write-Host "Certificat à approuver sur les appareils : $(Join-Path $taskData 'root.crt')"
            }
            if (-not $NoBrowser) { Start-Process $taskUrl }
        }
        'stop' { Invoke-Docker ($taskCompose + @('down')) }
        'status' { Invoke-Docker ($taskCompose + @('ps')) }
        'open' { Start-Process $taskUrl }
        'certificate' {
            if ($taskRouting['CADDY_PROFILE'] -ne 'private') { throw 'Le mode public utilise un certificat public.' }
            Invoke-Docker ($taskCompose + @('cp', 'caddy:/data/caddy/pki/authorities/local/root.crt',
                (Join-Path $taskData 'root.crt')))
        }
    }
} finally {
    Pop-Location
    foreach ($key in $taskKeys) {
        if ($null -eq $taskSaved[$key]) { Remove-Item -LiteralPath "Env:$key" -ErrorAction SilentlyContinue }
        else { Set-Item -LiteralPath "Env:$key" -Value $taskSaved[$key] }
    }
}
