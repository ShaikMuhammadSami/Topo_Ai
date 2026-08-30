import json

from topo_cli.config import (
    Profile,
    TopoConfig,
    load_config,
    save_config,
)


def test_configuration_does_not_store_token(
    tmp_path,
    monkeypatch,
) -> None:
    path = (
        tmp_path
        / "config.json"
    )

    monkeypatch.setenv(
        "TOPO_CONFIG_FILE",
        str(path),
    )

    config = TopoConfig(
        active_profile="test",
        profiles={
            "test": Profile(
                api_url=(
                    "https://topo.example"
                ),
                token_env=(
                    "TOPO_TEST_TOKEN"
                ),
                verify_tls=True,
                timeout=15.0,
                tenant_id="tenant:11111111-1111-4111-8111-111111111111",
                max_retries=4,
                retry_backoff=1.0,
            )
        },
    )

    save_config(config)

    raw = path.read_text(
        encoding="utf-8"
    )

    assert "secret-token" not in raw
    assert "token_env" in raw

    loaded = load_config()
    assert loaded.profiles["test"].tenant_id == "tenant:11111111-1111-4111-8111-111111111111"

    assert (
        loaded.active_profile
        == "test"
    )

    assert (
        loaded.profiles["test"]
        .max_retries
        == 4
    )

    value = json.loads(raw)

    assert "token" not in (
        value["profiles"]["test"]
    )
