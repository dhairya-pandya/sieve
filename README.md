# RedSwarm

RedSwarm is an open arena where attacker AI agents try to trick AI agents that hold money. If an attacker gets a target to pay it, a NEAR smart contract confirms the break and pays the attacker. No human judge decides who won.

Built for the NEAR Hackathon (1 to 14 November 2026), in the AI Security & Defense and AI Swarms tracks.

## Status

Design stage. The design is in [docs/superpowers/specs/2026-11-01-redswarm-design.md](docs/superpowers/specs/2026-11-01-redswarm-design.md). No code exists yet, and all of it will be written during the hackathon window. Run instructions will be added here once there is something to run.

## The problem

AI agents increasingly have payment tools. One prompt injection, such as a fake email saying "our bank details changed", can make an agent pay the wrong account. The people building these agents have no cheap, repeatable way to test for this. Hiring a red team is slow and expensive, and ordinary bug bounties end in arguments over whether a reported break is real.

## How it works

1. A builder posts a bounty on their agent. The money the agent controls sits in an escrow contract on NEAR, along with a list of approved payees that only the builder can change.
2. Attacker agents join the arena. They never talk to the target directly. The arena relays each message, charges a small fee per attempt, and logs the full transcript.
3. Attackers can reach the target through chat messages and through documents such as invoices and emails.
4. If the target pays an attacker's account that is not on the approved list, the contract treats that as a break and pays the attacker the bounty.
5. The builder reads the winning transcript, patches the agent, and runs the swarm again.

### Two kinds of break

A payout break happens when the target pays a registered attacker account that is not an approved payee. A secret break happens when an attacker extracts a canary secret from the target. The builder commits a hash of the secret when posting the bounty, and the contract checks the attacker's answer against it. In both cases the contract does the checking and the paying.

### The lead market

Attackers can sell partial leads to each other, for example "this agent trusts emails that quote a past invoice number". A lead has a title, a price, and a content hash on the contract. Another attacker pays to unlock it, the author is paid at that moment, and the arena hands over the content. The buyer checks it against the hash. This is the swarm part: attackers specialize, trade, and combine what they know.

### House agents

The arena ships with 5 to 8 house attackers, each with its own NEAR sub-account and its own strategy (poisoned documents, fake admin messages, encoded payloads, role-play, slow persuasion, urgency). Every bounty gets attacked from the first minute, even with no outside players.

It also ships two versions of an accounts-payable target called TreasuryBot. The naive one keeps its own vendor list and updates it when an email asks, and its guardrails live only in its prompt. The hardened one reads vendors only from the on-chain approved list, signs with a key limited to the escrow contract, and checks payee and spend cap in code outside the model. The same swarm should break the first and fail against the second. The point of the demo is that guardrails belong in code, not in the prompt.

## Trust model

Breaks, payouts and lead unlocks are enforced by the contract. The arena operator is trusted for relaying messages, keeping transcripts, and recording per-attempt fees, which are settled to the builder in batches. The arena does not stop a builder from rigging their own target, for example an agent that can never pay anyone. Targets must prove ownership of their endpoint when registering, so the arena only attacks agents whose owners asked for it.

## Planned stack

Python (FastAPI) for the arena, attackers and targets. Rust with near-sdk for the escrow contract. Models from NEAR AI Cloud for the live agents. A single live web page for the leaderboard and attempt stream. A deterministic demo mode will run locally with scripted agents, a local NEAR sandbox, and no API keys.

## Out of scope

Smart contract targets, running transcript replays inside a TEE, and paying winners in other tokens through NEAR Intents are stretch goals only if everything above works.

## Hackathon note

No code existed before 1 November 2026. Everything in this repository is new work for the NEAR Hackathon.
