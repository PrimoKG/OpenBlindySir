"""Exercise Windows launchers with synthetic state and a Docker function, never the daemon."""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
POWERSHELL = shutil.which("powershell")
pytestmark = pytest.mark.skipif(os.name != "nt" or not POWERSHELL, reason="Windows ACLs")


def quote(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def run_script(script: str) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL
    env = dict(os.environ)
    env.pop("PSModulePath", None)
    return subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-Command",
            "$taskSecurity = Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Security'; "
            "Import-Module (Join-Path $taskSecurity 'Microsoft.PowerShell.Security.psd1'); "
            + script,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        env=env,
    )


@pytest.fixture
def installation(tmp_path: Path) -> Path:
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in (
        "docker-host.ps1",
        "docker-context.ps1",
        "file-integrity.ps1",
        "private-config.ps1",
        "pack-maintenance.ps1",
    ):
        shutil.copyfile(ROOT / "tools" / name, tools / name)
    (tmp_path / "music").mkdir()
    return tmp_path


def test_init_protects_windows_secrets_before_docker_writes(installation: Path) -> None:
    script = f"""
    $ErrorActionPreference = 'Stop'
    $taskFixture = {quote(installation)}
    $taskIcacls = Join-Path $env:SYSTEMROOT 'System32/icacls.exe'
    & $taskIcacls $taskFixture /grant '*S-1-1-0:(OI)(CI)RX' | Out-Null
    if ($LASTEXITCODE -ne 0) {{ throw 'Synthetic parent ACL unavailable' }}
    function docker {{
        if ($args[0] -ne 'run') {{ throw 'Unexpected Docker action' }}
        $taskFile = Join-Path $taskFixture '.local/docker/hosting.env'
        Set-Content -LiteralPath $taskFile -Value 'SYNTHETIC_SECRET=example' -Encoding UTF8
        $global:LASTEXITCODE = 0
    }}
    $taskLauncher = Join-Path $taskFixture 'tools/docker-host.ps1'
    $taskMusic = Join-Path $taskFixture 'music'
    & $taskLauncher -Action init -Address '127.0.0.1:8443' -MusicDir $taskMusic -NoBuild
    $taskOwner = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    foreach ($taskPath in @('.local/docker', '.local/docker/hosting.env')) {{
        $taskPermissions = Get-Acl -LiteralPath (Join-Path $taskFixture $taskPath)
        if (-not $taskPermissions.AreAccessRulesProtected) {{ throw 'Inherited secret ACL' }}
        foreach ($taskRule in $taskPermissions.Access) {{
            $taskIdentity = $taskRule.IdentityReference
            $taskSid = $taskIdentity.Translate([Security.Principal.SecurityIdentifier])
            if ($taskSid.Value -ne $taskOwner) {{ throw 'Secret readable by another identity' }}
        }}
    }}
    """
    result = run_script(script)
    assert result.returncode == 0, result.stdout + result.stderr


def test_config_without_write_dacl_is_replaced_privately_without_changing_content(
    installation: Path,
) -> None:
    result = run_script(f"""
    $ErrorActionPreference = 'Stop'
    . {quote(installation / "tools/private-config.ps1")}
    $taskConfig = Join-Path {quote(installation)} '.local/docker'
    New-TaskPrivateDirectory $taskConfig
    $taskFile = Join-Path $taskConfig 'hosting.env'
    $taskData = [Text.Encoding]::UTF8.GetBytes('SYNTHETIC_SECRET=example')
    [IO.File]::WriteAllBytes($taskFile, $taskData)
    $taskOwner = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $taskRights = New-Object Security.Principal.SecurityIdentifier('S-1-3-4')
    $taskAcl = New-Object Security.AccessControl.FileSecurity
    $taskAcl.SetAccessRuleProtection($true, $false)
    foreach ($taskIdentity in @($taskOwner, $taskRights)) {{
        $taskRule = New-Object Security.AccessControl.FileSystemAccessRule(
            $taskIdentity, 'Modify', 'Allow')
        $taskAcl.AddAccessRule($taskRule)
    }}
    (Get-Item -LiteralPath $taskFile).SetAccessControl($taskAcl)
    Protect-TaskPath $taskFile
    $taskAfter = Get-Acl -LiteralPath $taskFile
    if (-not $taskAfter.AreAccessRulesProtected -or $taskAfter.Access.Count -ne 1) {{
        throw 'Configuration remains shared'
    }}
    if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($taskFile)) -ne
        [Convert]::ToBase64String($taskData)) {{ throw 'Configuration content changed' }}
    if (Get-ChildItem -LiteralPath $taskConfig -Filter '.private-config-*') {{
        throw 'Private temporary file leaked'
    }}
    """)
    assert result.returncode == 0, result.stdout + result.stderr


def mock_docker(root: Path, *, fail_copy: bool = False) -> str:
    return f"""
    $taskFixture = {quote(root)}
    function docker {{
        $global:LASTEXITCODE = 0
        $taskLine = $args | ConvertTo-Json -Compress
        Add-Content -LiteralPath (Join-Path $taskFixture 'docker.log') -Value $taskLine
        if ($args[0] -eq 'inspect') {{
            if ($args -contains '{{{{.State.Running}}}}') {{ return 'true' }}
            if ($args -contains '{{{{.Image}}}}') {{ return ('sha256:' + ('a' * 64)) }}
            if ($args -contains '{{{{json .Mounts}}}}') {{
                $taskVolume = 'example_app_data'
                if ($args[1] -eq 'openblindysir-bridge-1') {{ $taskVolume = 'example_bridge_data' }}
                return ('[{{"Destination":"/data","Name":"' + $taskVolume + '"}}]')
            }}
        }}
        if ($args[0] -eq 'cp') {{
            if ({"$true" if fail_copy else "$false"}) {{ $global:LASTEXITCODE = 9; return }}
            if ($args[1] -match ':/data/state$') {{
                $taskState = Join-Path $args[2] 'state'
                New-Item -ItemType Directory -Path $taskState -Force | Out-Null
                $taskFile = Join-Path $taskState 'session.json'
                Set-Content -LiteralPath $taskFile -Value '{{"format":8}}'
            }} else {{ Set-Content -LiteralPath $args[2] -Value 'SYNTHETIC_BRIDGE=example' }}
        }}
        if ($args[0] -eq 'compose' -and $args -contains 'cp') {{
            Set-Content -LiteralPath $args[-1] -Value 'SYNTHETIC_CERTIFICATE=example'
        }}
    }}
    """


@pytest.mark.parametrize("failure", [False, True])
def test_backup_quiesces_writers_and_restarts_after_copy_failure(
    installation: Path, failure: bool
) -> None:
    config = installation / ".local/docker"
    config.mkdir(parents=True)
    (config / "hosting.env").write_text(
        "DOMAIN=127.0.0.1:8443\nCADDY_PROFILE=private\nSYNTHETIC_SECRET=example\n", encoding="utf-8"
    )
    result = run_script(
        "$ErrorActionPreference = 'Stop'; "
        + mock_docker(installation, fail_copy=failure)
        + f"& {quote(installation / 'tools/pack-maintenance.ps1')} -Action backup"
    )
    assert (result.returncode != 0) is failure, result.stdout + result.stderr
    commands = [json.loads(line) for line in (installation / "docker.log").read_text().splitlines()]
    first_copy = next(i for i, args in enumerate(commands) if args[0] == "cp")
    stopped = {arg for args in commands[:first_copy] if args[0] == "stop" for arg in args[1:]}
    resumed = {arg for args in commands[first_copy:] if args[0] == "start" for arg in args[1:]}
    services = {f"openblindysir-{name}-1" for name in ("app", "bridge", "caddy")}
    assert services <= stopped
    assert services <= resumed
    if not failure:
        backup = next((installation / ".local/backups").iterdir())
        assert (backup / "bridge-config.toml").is_file()
        record = json.loads((backup / "backup.json").read_text(encoding="utf-8-sig"))
        assert record["bridge_volume"] == "example_bridge_data"


@pytest.mark.parametrize("failure", [False, True])
def test_update_secures_configuration_and_recovers_when_start_fails(
    installation: Path, failure: bool
) -> None:
    config = installation / ".local/docker"
    config.mkdir(parents=True)
    (config / "hosting.env").write_text(
        "DOMAIN=127.0.0.1:8443\nCADDY_PROFILE=private\nSYNTHETIC_SECRET=example\n", encoding="utf-8"
    )
    next_pack = installation / "next-pack"
    tools = next_pack / "tools"
    tools.mkdir(parents=True)
    (tools / "load-pack.ps1").write_text("# Synthetic verified loader\n", encoding="utf-8-sig")
    (tools / "docker-host.ps1").write_text(
        "param($Action, [switch]$NoBuild, [switch]$NoBrowser)\n"
        + ("if ($Action -eq 'start') { throw 'Synthetic start failure' }\n" if failure else ""),
        encoding="utf-8-sig",
    )
    result = run_script(
        "$ErrorActionPreference = 'Stop'; "
        + mock_docker(installation)
        + f"& {quote(installation / 'tools/pack-maintenance.ps1')} -Action update "
        + f"-PackDirectory {quote(next_pack)}"
        + f"; $taskAcl = Get-Acl -LiteralPath {quote(next_pack / '.local/docker/hosting.env')}; "
        + "if (-not $taskAcl.AreAccessRulesProtected) { throw 'Inherited secret ACL' }"
    )
    assert (result.returncode != 0) is failure, result.stdout + result.stderr
    assert (next_pack / ".local/docker/hosting.env").is_file()
    if failure:
        assert "previous state, Bridge and images were restored" in result.stderr
        commands = [
            json.loads(line) for line in (installation / "docker.log").read_text().splitlines()
        ]
        restores = [args for args in commands if args[0] == "run"]
        assert len(restores) == 2
        assert "--directory" in restores[0]
        assert "--file" in restores[1]
        assert any(args[0] == "compose" and "up" in args for args in commands)


def test_rollback_rejects_incomplete_backup_before_stopping(installation: Path) -> None:
    backup = installation / "incomplete"
    backup.mkdir()
    (backup / "hashes.json").write_text("{}", encoding="utf-8")
    result = run_script(
        "$ErrorActionPreference = 'Stop'; "
        + mock_docker(installation)
        + f"& {quote(installation / 'tools/pack-maintenance.ps1')} -Action rollback "
        + f"-BackupDirectory {quote(backup)} -ConfirmRollback"
    )
    assert result.returncode != 0
    assert "Incomplete backup" in result.stderr
    assert not (installation / "docker.log").exists()


@pytest.mark.parametrize("failure", [False, True])
def test_rollback_pins_original_images_and_recovers_after_failed_restore(
    installation: Path, failure: bool
) -> None:
    config = installation / ".local/docker"
    config.mkdir(parents=True)
    (config / "hosting.env").write_text(
        "DOMAIN=127.0.0.1:8443\nCADDY_PROFILE=private\n", encoding="utf-8"
    )
    backup_result = run_script(
        mock_docker(installation)
        + f"& {quote(installation / 'tools/pack-maintenance.ps1')} -Action backup"
    )
    assert backup_result.returncode == 0, backup_result.stdout + backup_result.stderr
    backup = next((installation / ".local/backups").iterdir())
    record_path = backup / "backup.json"
    record = json.loads(record_path.read_text(encoding="utf-8-sig"))
    record["images"] = {name: "sha256:" + "b" * 64 for name in ("app", "bridge", "caddy")}
    record_path.write_text(json.dumps(record), encoding="utf-8")
    hashes = json.loads((backup / "hashes.json").read_text(encoding="utf-8-sig"))
    hashes["backup.json"] = hashlib.sha256(record_path.read_bytes()).hexdigest()
    (backup / "hashes.json").write_text(json.dumps(hashes), encoding="utf-8")
    script = mock_docker(installation)
    if failure:
        script += """
        $taskDocker = ${function:docker}
        $global:taskRestoreFailed = $false
        function docker {
            & $taskDocker @args
            if ($args[0] -eq 'run' -and -not $global:taskRestoreFailed) {
                $global:taskRestoreFailed = $true
                $global:LASTEXITCODE = 9
            }
        }
        """
    result = run_script(
        script
        + f"& {quote(installation / 'tools/pack-maintenance.ps1')} -Action rollback "
        + f"-BackupDirectory {quote(backup)} -ConfirmRollback"
    )
    assert (result.returncode != 0) is failure, result.stdout + result.stderr
    override = (config / "rollback.override.yaml").read_text(encoding="utf-8-sig")
    expected_image = "a" if failure else "b"
    assert override.count("sha256:" + expected_image * 64) == 3
    if failure:
        assert "state from before this attempt was restored" in result.stderr
