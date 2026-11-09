import math

from sieve.signals import duplicates, sybil

NOW_NS = 1_800_000_000 * 10**9
DAY_NS = 86_400 * 10**9


def test_duplicates_cosine():
    vectors = {"a": [1.0, 0.0], "b": [0.99, 0.141], "c": [0.0, 1.0]}
    props = [{"id": 1, "text": "a"}, {"id": 2, "text": "b"}, {"id": 3, "text": "c"}]
    out = duplicates(props, embed=lambda texts: [vectors[t] for t in texts], threshold=0.9)
    assert [pid for pid, _ in out[1]] == [2] and [pid for pid, _ in out[2]] == [1]
    assert out[3] == []
    assert math.isclose(out[1][0][1], 0.99, abs_tol=0.01)


def test_sybil_shared_funder():
    accounts = {
        "alice.testnet": {"created": {"block_timestamp": str(NOW_NS - 2 * DAY_NS), "transaction_hash": "T1"}},
        "bob.testnet": {"created": {"block_timestamp": str(NOW_NS - 1 * DAY_NS), "transaction_hash": "T2"}},
        "carol.testnet": {"created": {"block_timestamp": str(NOW_NS - 400 * DAY_NS), "transaction_hash": "T3"}},
    }
    txns = {"T1": {"signer_account_id": "farm.testnet"}, "T2": {"signer_account_id": "farm.testnet"},
            "T3": {"signer_account_id": "testnet"}}

    def fetch(path: str) -> dict:
        kind, key = path.split("/")[2:4]
        return {"data": accounts[key] if kind == "accounts" else txns[key]}

    out = sybil(list(accounts), fetch=fetch, now_ns=NOW_NS)
    assert out["alice.testnet"] == {"age_days": 2, "created_by": "farm.testnet", "shares_creator_with": ["bob.testnet"]}
    assert out["carol.testnet"]["shares_creator_with"] == [] and out["carol.testnet"]["age_days"] == 400
