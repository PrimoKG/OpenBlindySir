# BuildKit can traverse inaccessible ignored folders when an allowlist uses ! rules.
# Copy only build inputs to a fresh context; never enumerate the whole checkout.
function New-DockerBuildContext([string]$Root, [string]$Parent) {
    $context = Join-Path $Parent ('build-context-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $context -Force | Out-Null
    try {
        $files = @('Dockerfile', '.dockerignore', 'pyproject.toml', 'uv.lock', 'VERSION', 'LICENSE',
            'protocol/pyproject.toml', 'server/pyproject.toml', 'bridge/pyproject.toml',
            'tools/host_pc.py', 'tools/docker_config.py', 'tools/docker_bridge.py',
            'web/package.json', 'web/package-lock.json', 'web/index.html', 'web/vite.config.ts')
        $files += @(Get-ChildItem -LiteralPath (Join-Path $Root 'web') -Filter 'tsconfig*.json' -File |
            ForEach-Object { 'web/' + $_.Name })
        foreach ($relative in $files) {
            $source = Get-Item -LiteralPath (Join-Path $Root $relative) -Force
            if ($source.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Build input must not be a link: $relative"
            }
            $destination = Join-Path $context $relative
            New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
            Copy-Item -LiteralPath $source.FullName -Destination $destination
        }
        foreach ($relative in @('protocol/src', 'server/src', 'bridge/src', 'web/src')) {
            Copy-DockerSourceTree (Join-Path $Root $relative) (Join-Path $context $relative)
        }
        if (Test-Path -LiteralPath (Join-Path $Root 'web/public')) {
            Copy-DockerSourceTree (Join-Path $Root 'web/public') (Join-Path $context 'web/public')
        }
        return $context
    } catch {
        Remove-DockerBuildContext $context $Parent
        throw
    }
}

function Copy-DockerSourceTree([string]$Source, [string]$Destination) {
    $sourceDirectory = Get-Item -LiteralPath $Source -Force
    if ($sourceDirectory.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Build input must not be a link: $Source"
    }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    foreach ($item in Get-ChildItem -LiteralPath $Source -Force) {
        if ($item.Name -in @('__pycache__', 'node_modules', 'test-results', 'dist', '.git', '.local', '.venv')) {
            continue
        }
        if ($item.Name -like '.env*' -or $item.Extension -in @('.pyc', '.mp3', '.flac', '.wav',
            '.m4a', '.ogg', '.opus', '.pem', '.key', '.crt')) { continue }
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Build input must not be a link: $($item.FullName)"
        }
        $target = Join-Path $Destination $item.Name
        if ($item.PSIsContainer) { Copy-DockerSourceTree $item.FullName $target }
        else { Copy-Item -LiteralPath $item.FullName -Destination $target }
    }
}

function Remove-DockerBuildContext([string]$Context, [string]$Parent) {
    $resolved = (Resolve-Path -LiteralPath $Context).Path
    $resolvedParent = (Resolve-Path -LiteralPath $Parent).Path
    if ((Split-Path -Parent $resolved) -ne $resolvedParent -or
        (Split-Path -Leaf $resolved) -notmatch '^build-context-[a-f0-9]{32}$') {
        throw 'Refusing to remove a directory outside the generated Docker context.'
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
