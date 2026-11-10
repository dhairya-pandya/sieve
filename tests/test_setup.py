import asyncio

from sieve.near import NEAR
from sieve.setup import grant_round, prompt


class RecordingNear:
    def __init__(self):
        self.calls = []

    async def call(self, signer, contract, method, args, deposit=0, **kw):
        self.calls.append((signer, contract, method, args, deposit))
        return 2 if method == "create_round" else None


def test_grant_round_uses_hardened_rubric_with_milestones():
    near = RecordingNear()
    round_id = asyncio.run(grant_round(near, "op.testnet", "sieve.op.testnet", "demo.sputnikv2.testnet"))
    assert round_id == 2
    (_, _, m1, create, deposit), (_, _, m2, milestones, _) = near.calls
    assert m1 == "create_round" and deposit == NEAR
    assert create["system"] == prompt("grant_v1")
    assert create["threshold"] == 7 and create["tranche"] == str(NEAR)
    assert m2 == "set_milestones"
    assert milestones == {"round_id": 2, "milestone_system": prompt("milestone_v1"),
                          "newcomer_tranche": str(NEAR // 5), "tranches": 3}
