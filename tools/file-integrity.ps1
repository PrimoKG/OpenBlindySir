function Get-TaskSha256([string]$LiteralPath) {
    # Works in Windows PowerShell 5.1 and PowerShell 7, including child processes
    # whose inherited module path prevents Get-FileHash from being auto-loaded.
    $taskStream = [IO.File]::OpenRead($LiteralPath)
    $taskHasher = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($taskHasher.ComputeHash($taskStream)).Replace('-', '') }
    finally { $taskHasher.Dispose(); $taskStream.Dispose() }
}
