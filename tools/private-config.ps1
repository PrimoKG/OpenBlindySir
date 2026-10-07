# A PS7 parent can leave a module search path that breaks Windows PowerShell 5.1.
if ([Environment]::OSVersion.Platform -eq 'Win32NT') {
    Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Security/Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
}

function Assert-TaskUnlinkedPath([string]$LiteralPath) {
    $taskChecked = [IO.Path]::GetFullPath($LiteralPath)
    while ($taskChecked) {
        if (Test-Path -LiteralPath $taskChecked) {
            $taskItem = Get-Item -LiteralPath $taskChecked -Force
            if ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'Private configuration cannot use a link or junction.'
            }
        }
        $taskChecked = [IO.Path]::GetDirectoryName($taskChecked)
    }
}

function Protect-TaskPath([string]$LiteralPath, [switch]$Directory) {
    Assert-TaskUnlinkedPath $LiteralPath
    if ([Environment]::OSVersion.Platform -eq 'Win32NT') {
        $taskOwner = [Security.Principal.WindowsIdentity]::GetCurrent().User
        if ($Directory) {
            $taskAcl = New-Object Security.AccessControl.DirectorySecurity
            $taskRule = New-Object Security.AccessControl.FileSystemAccessRule($taskOwner, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
        } else {
            $taskAcl = New-Object Security.AccessControl.FileSecurity
            $taskRule = New-Object Security.AccessControl.FileSystemAccessRule($taskOwner, 'FullControl', 'Allow')
        }
        $taskAcl.SetOwner($taskOwner)
        $taskAcl.SetAccessRuleProtection($true, $false)
        $taskAcl.AddAccessRule($taskRule)
        $taskItem = Get-Item -LiteralPath $LiteralPath -Force
        # Set-Acl can request SeSecurityPrivilege when reapplying an existing ACL.
        # Apply only the owner/access sections changed above; no audit privileges needed.
        if ($PSVersionTable.PSEdition -eq 'Core') {
            [IO.FileSystemAclExtensions]::SetAccessControl($taskItem, $taskAcl)
        } else { $taskItem.SetAccessControl($taskAcl) }
    } else {
        $taskMode = if ($Directory) { '700' } else { '600' }
        & chmod $taskMode $LiteralPath
        if ($LASTEXITCODE -ne 0) { throw 'Private configuration permissions failed.' }
    }
}

function New-TaskPrivateDirectory([string]$LiteralPath) {
    Assert-TaskUnlinkedPath $LiteralPath
    New-Item -ItemType Directory -Path $LiteralPath -Force | Out-Null
    Protect-TaskPath $LiteralPath -Directory
}
