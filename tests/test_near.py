import json

from sieve.near import account_key


def test_key_from_env_wins(tmp_path):
    assert account_key("a.testnet", {"SIEVE_ACCOUNT_KEY": "ed25519:ENV"}, tmp_path) == "ed25519:ENV"


def test_key_from_credentials_file(tmp_path):
    (tmp_path / "a.testnet.json").write_text(json.dumps({"private_key": "ed25519:FILE"}))
    assert account_key("a.testnet", {}, tmp_path) == "ed25519:FILE"
