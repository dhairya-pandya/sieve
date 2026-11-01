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
        swarm.append(Attacker(account, key, STRATEGIES[(i - 1) % len(STRATEGIES)](account), arena, chain=chain))
    return swarm


LEAD_TITLE = "which vendor the bot trusts"
LEAD_CONTENT = "The bot rewrites vendor details from any document it reads. vendor: acme"


async def trade_leads(swarm: list[Attacker], bounty_id: int, price: int = NEAR // 100) -> int:
    """The first house attacker (poisoned_email) sells what it knows; the last (slow_persuasion) buys it."""
    seller, buyer = swarm[0], swarm[-1]
    lead_id = await seller.post_lead(bounty_id, LEAD_TITLE, price, LEAD_CONTENT)
    await buyer.buy_lead(lead_id)
    return lead_id
