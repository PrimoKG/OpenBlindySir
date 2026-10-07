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
        # Keep the existing owner. Changing ownership is unnecessary for privacy
        # and can require extra privileges even for a newly created NTFS directory.
        $taskAcl.SetAccessRuleProtection($true, $false)
        $taskAcl.AddAccessRule($taskRule)
        $taskItem = Get-Item -LiteralPath $LiteralPath -Force
        # Set-Acl can request SeSecurityPrivilege when reapplying an existing ACL.
        # Apply only the access section changed above; no audit/owner privileges needed.
        try {
            if ($PSVersionTable.PSEdition -eq 'Core') {
                [IO.FileSystemAclExtensions]::SetAccessControl($taskItem, $taskAcl)
            } else { $taskItem.SetAccessControl($taskAcl) }
        } catch {
            $taskDenied = $_.Exception -is [UnauthorizedAccessException] -or $_.Exception.InnerException -is [UnauthorizedAccessException]
            if ($Directory -or -not $taskDenied) { throw }
            # An older file may belong to another account and allow reading/renaming,
            # but not changing its ACL. Publish an identical private file atomically.
            Copy-TaskPrivateReplacement $LiteralPath
        }
    } else {
        $taskMode = if ($Directory) { '700' } else { '600' }
        & chmod $taskMode $LiteralPath
        if ($LASTEXITCODE -ne 0) { throw 'Private configuration permissions failed.' }
    }
}

function Copy-TaskPrivateReplacement([string]$LiteralPath) {
    $taskOriginal = [IO.Path]::GetFullPath($LiteralPath)
    Assert-TaskUnlinkedPath $taskOriginal
    $taskParent = [IO.Path]::GetDirectoryName($taskOriginal)
    Protect-TaskPath $taskParent -Directory
    $taskStage = Join-Path $taskParent ('.private-config-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    if ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($taskStage)) -ne $taskParent) { throw 'Invalid private temporary path.' }
    $taskRead = $null
    $taskWrite = $null
    try {
        $taskRead = [IO.File]::Open($taskOriginal, 'Open', 'Read', 'Read')
        $taskWrite = [IO.File]::Open($taskStage, 'CreateNew', 'Write', 'None')
        $taskRead.CopyTo($taskWrite)
        $taskWrite.Flush($true)
        $taskWrite.Dispose(); $taskWrite = $null
        $taskRead.Dispose(); $taskRead = $null
        Protect-TaskPath $taskStage
        if (-not ('OpenBlindySir.PrivateConfig.Native' -as [type])) {
            Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace OpenBlindySir.PrivateConfig {
    public static class Native {
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool MoveFileEx(string source, string destination, uint flags);
    }
}
'@
        }
        # Same directory/volume, replace existing + write through. File.Replace would
        # preserve the old ACL; MoveFileEx retains the new file's private permissions.
        if (-not [OpenBlindySir.PrivateConfig.Native]::MoveFileEx($taskStage, $taskOriginal, 9)) {
            throw (New-Object ComponentModel.Win32Exception([Runtime.InteropServices.Marshal]::GetLastWin32Error()))
        }
    } finally {
        if ($taskRead) { $taskRead.Dispose() }
        if ($taskWrite) { $taskWrite.Dispose() }
        if (Test-Path -LiteralPath $taskStage) { [IO.File]::Delete($taskStage) }
    }
}

function New-TaskPrivateDirectory([string]$LiteralPath) {
    Assert-TaskUnlinkedPath $LiteralPath
    New-Item -ItemType Directory -Path $LiteralPath -Force | Out-Null
    Protect-TaskPath $LiteralPath -Directory
}
