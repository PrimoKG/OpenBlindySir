# Local Windows assistant. No service, no Docker socket exposed to a web page.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName Microsoft.VisualBasic
$taskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$taskForm = New-Object Windows.Forms.Form
$taskForm.Text = 'OpenBlindySir · FR / EN'
$taskForm.Size = New-Object Drawing.Size(610, 560)
$taskForm.StartPosition = 'CenterScreen'
$taskLog = New-Object Windows.Forms.TextBox
$taskLog.Multiline = $true
$taskLog.ReadOnly = $true
$taskLog.ScrollBars = 'Vertical'
$taskLog.Location = New-Object Drawing.Point(20, 235)
$taskLog.Size = New-Object Drawing.Size(550, 250)
$taskForm.Controls.Add($taskLog)
$taskActions = @(@('Configurer / Setup','init'), @('Démarrer / Start','start'), @('Arrêter / Stop','stop'), @('État / Status','status'), @('Ouvrir / Open','open'), @('Certificat / Certificate','certificate'), @('Sauvegarder / Backup','backup'), @('Mettre à jour / Update','update'), @('Restaurer / Rollback','rollback'))
for ($index = 0; $index -lt $taskActions.Count; $index++) {
    $taskButton = New-Object Windows.Forms.Button
    $taskButton.Text = $taskActions[$index][0]
    $taskButton.Tag = $taskActions[$index][1]
    $taskButton.Location = New-Object Drawing.Point((20 + ($index % 3) * 185), (20 + [Math]::Floor($index / 3) * 65))
    $taskButton.Size = New-Object Drawing.Size(175, 50)
    $taskButton.Add_Click({
        $taskAction = $this.Tag
        try {
            if ($taskAction -in @('backup','update','rollback')) {
                $taskMaintenance = @{Action=$taskAction}
                if ($taskAction -ne 'backup') {
                    $taskPicker = New-Object Windows.Forms.FolderBrowserDialog
                    $taskPicker.Description = if ($taskAction -eq 'update') { 'Nouveau pack / New pack' } else { 'Sauvegarde privée / Private backup' }
                    if ($taskPicker.ShowDialog() -ne 'OK') { return }
                    if ($taskAction -eq 'update') { $taskMaintenance.PackDirectory = $taskPicker.SelectedPath }
                    else {
                        if ([Windows.Forms.MessageBox]::Show('Remplacer la session par cette sauvegarde ? Les réponses et points ultérieurs seront conservés dans une nouvelle sauvegarde. / Replace the session with this backup? Later answers and scores will be saved in a new backup.', 'Rollback', 'YesNo') -ne 'Yes') { return }
                        $taskMaintenance.BackupDirectory = $taskPicker.SelectedPath
                        $taskMaintenance.ConfirmRollback = $true
                    }
                }
                $taskLog.Text = (& (Join-Path $taskRoot 'tools/pack-maintenance.ps1') @taskMaintenance 6>&1 2>&1 | Out-String)
                if ($taskAction -eq 'update') { $script:taskRoot = (Resolve-Path -LiteralPath $taskMaintenance.PackDirectory).Path }
                return
            }
            $taskArgs = @{Action=$taskAction; NoBuild=$true; NoBrowser=$true}
            if ($taskAction -eq 'init') {
                $taskPicker = New-Object Windows.Forms.FolderBrowserDialog
                if ($taskPicker.ShowDialog() -ne 'OK') { return }
                $taskAddress = [Microsoft.VisualBasic.Interaction]::InputBox('Adresse LAN/VPN (ex. 192.168.1.21:8443) / LAN or VPN address', 'OpenBlindySir')
                if (-not $taskAddress) { return }
                $taskArgs.MusicDir = $taskPicker.SelectedPath
                $taskArgs.Address = $taskAddress
            }
            $taskOutput = & (Join-Path $taskRoot 'tools/docker-host.ps1') @taskArgs 6>&1 2>&1 | Out-String
            $taskLog.Text = $taskOutput
        } catch { $taskLog.Text = $_.Exception.Message }
    })
    $taskForm.Controls.Add($taskButton)
}
[void]$taskForm.ShowDialog()
