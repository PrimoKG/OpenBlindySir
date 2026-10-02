"""Compose setup keeps origins, port mappings and private state consistent."""

from pathlib import Path

import pytest

from docker_config import dotenv_quote, write_docker_config
from host_pc import HostingError
from openblindysir_server.config import read_dotenv


@pytest.mark.parametrize(
    ("address", "mode", "expected"),
    [
        ("127.0.0.1:8443", "private", ("127.0.0.1:8443", "127.0.0.1", "8443")),
        ("localhost:8443", "private", ("localhost:8443", "127.0.0.1", "8443")),
        ("25.1.2.3:8443", "private", ("25.1.2.3:8443", "25.1.2.3", "8443")),
        ("[::1]:8443", "private", ("[::1]:8443", "::1", "8443")),
        ("blind.example.com:443", "public", ("blind.example.com", "0.0.0.0", "443")),
    ],
)
def test_routing_and_secrets(tmp_path: Path, address: str, mode: str, expected: tuple) -> None:
    path = tmp_path / "hosting.env"
    write_docker_config(path, address=address, mode=mode, music_dir="/example music")
    config = read_dotenv(path)
    assert (config["DOMAIN"], config["BIND_IP"], config["HTTPS_PORT"]) == expected
    assert ":8443" not in config["TLS_HOST"]
    assert config["CADDY_PROFILE"] == mode
    assert len(config["BLIND_PASSWORD"]) >= 12
    assert config["BLIND_PASSWORD"] != config["HOST_PASSWORD"]
    assert len(config["BRIDGE_SECRET"]) >= 32
    assert config["BRIDGE_DEMO"] == "false"
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_existing_configuration_is_preserved(tmp_path: Path) -> None:
    path = tmp_path / "hosting.env"
    path.write_text("example-existing", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_docker_config(path, address="localhost:8443", mode="private", music_dir="/music")
    assert path.read_text() == "example-existing"


@pytest.mark.parametrize("value", ["/music\nDOMAIN=wrong", "/music\rwrong", "/music\x00wrong"])
def test_multiline_paths_are_refused(value: str) -> None:
    with pytest.raises(HostingError):
        dotenv_quote(value)


def test_dollar_and_quote_are_literal() -> None:
    assert dotenv_quote("/example's $music") == "'/example\\'s $music'"


def test_invalid_config_does_not_create_file(tmp_path: Path) -> None:
    path = tmp_path / "hosting.env"
    with pytest.raises(HostingError):
        write_docker_config(path, address="0.0.0.0:8443", mode="private", music_dir="/music")
    assert not path.exists()
