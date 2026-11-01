from __future__ import annotations

from redswarm.attackers import strategies
from redswarm.attackers.base import ArenaClient, Attacker
from redswarm.chain.base import NEAR, Chain

STRATEGIES = [
    strategies.poisoned_email,
    strategies.fake_admin,
    strategies.urgency,
    strategies.encoded_payload,
    strategies.roleplay,
    strategies.slow_persuasion,
]


async def build_house_swarm(chain: Chain, arena: ArenaClient, n: int = 6,
                            funds: int = 20 * NEAR, credit: int = NEAR) -> list[Attacker]:
    """Create n funded attacker accounts (atk-1..atk-n), register them, and give each a strategy."""
    swarm = []
    for i in range(1, n + 1):
        account = await chain.create_account(f"atk-{i}", funds)
        await chain.register_attacker(account)
        await chain.deposit_credit(account, credit)
        key = await arena.register_attacker(account)
        swarm.append(Attacker(account, key, STRATEGIES[(i - 1) % len(STRATEGIES)](account), arena))
    return swarm
