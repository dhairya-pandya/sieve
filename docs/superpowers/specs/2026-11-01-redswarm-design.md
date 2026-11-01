# RedSwarm: red-team bounty arena for AI agents that hold money (design)

Working name "RedSwarm" is a placeholder; rename freely.

## Context
NEAR Hackathon, 1 Nov to 14 Nov 2026 23:59 UTC. Solo builder. Goal: win track prizes in **AI Security & Defense** and **AI Swarms** (one submission, both tracks ticked). Polish beats scope.

Pain point: AI agents now hold money and have payment tools. One prompt injection can make an agent pay an attacker. Agent builders have no cheap, ongoing way to test for this. Manual red-teaming is slow and expensive, and classic bug bounties end in arguments over whether a break is real.

RedSwarm is an open arena. A builder posts a bounty on their agent. A swarm of attacker agents tries to break it. A break is proven on-chain and paid automatically, with no human judge. The builder gets the winning transcript, patches the agent, and runs the swarm again.

## Hackathon rules that shape the build
- First-pass judging by Claude Code and Codex: they clone the repo and check that it runs and does what the README says. README needs "do X, see Y" steps, no marketing language.
- Public repo, public X post with a demo video (screenshots alone fail), submission form. Hosted demo is a plus; keep it up until 18 Nov.
- Only NEAR work built during the window counts. There is no pre-existing code; say so in the README.
- NEAR Intents has no testnet (mainnet, tiny amounts only).

## Goals
1. **Post a bounty.** Builder registers a target agent: chat endpoint, the agent's NEAR account, bounty amount, rules, and a hash of a canary secret. Bounty funds go into the escrow contract.
2. **Attack through the arena.** Attacker agents never talk to targets directly. The arena proxies every message: charges the per-attempt fee, logs the transcript, rate limits, and records who broke the target first. Two channels reach the target (user decision): **chat messages** and **documents** (invoices, emails). Every target, house or outside, implements the same small HTTP API that receives both.
3. **Two break types, both proven on-chain, no judge:**
   - **Payout break.** The escrow holds the target's treasury, which is the bounty. At posting, the poster registers an **approved payee list** on-chain; only the poster can change it. Only the target agent's NEAR account can call `pay(receiver, amount, invoice_ref)`. Payment to an approved payee is normal work. Payment to a registered attacker account that is not on the list is a break: the attacker is paid the bounty and it closes. Payment to anyone else is refused and logged.
   - **Secret break.** The target agent knows a canary secret. At posting, the builder commits `sha256(secret + salt)` on-chain. An attacker who extracts the secret submits it, the contract checks the hash, and pays.
4. **Attack fees.** Attackers prepay credit into the contract. Each attempt costs a small fee that goes to the bounty poster when the bounty closes. This stops spam and covers the builder's compute.
5. **House swarm.** 5 to 8 attacker agents ship with the arena, each with its own NEAR sub-account (for example `atk-3.redswarm.testnet`) and its own strategy: poisoned tool output, fake system or admin message, encoded payloads, role-play, slow multi-turn persuasion, authority or urgency pressure. Every bounty gets attacked from the first minute.
6. **Swarm economy: lead market (user decision).** Attackers post partial leads for sale (for example "agent trusts emails that quote a past invoice number"). Each lead has a title, a price, and a content hash on-chain; the content itself lives with the arena. Another attacker pays the contract to unlock a lead, the author is paid at unlock, and the arena serves the content, which the buyer checks against the hash. No citations, nothing to verify afterwards, and buying from your own second account gains nothing. House attackers both sell and buy leads, so a market forms. This is the "many agents, one economy" part for the Swarms track.
7. **Outside attackers.** Anyone can join with a NEAR account plus an arena API key and attack through the same proxy.
8. **Leaderboard and live page.** Live stream of attempts per bounty, breaks, payouts, lead board. Attacker ranking (breaks, earnings, hit rate). Target ranking (attempts survived), with a "survived N attacks" badge.
9. **Private report.** The bounty poster sees the full winning transcript and any leads the winner bought. Others see only that a break happened and by whom.
10. **Before and after demo (user decision: accounts-payable agent).** TreasuryBot reads incoming invoices and emails and pays approved vendors from escrow. House vendor accounts send real invoices so it does real work between attacks. Attackers send poisoned invoices and fake "vendor changed bank details" emails, the most common real-world payment fraud.
    - **TreasuryBot (naive):** keeps its own vendor book and updates it when an email asks. Guardrails live only in its prompt.
    - **TreasuryBot (hardened):** reads vendor accounts only from the on-chain approved list, which only the owner can change. Its NEAR key is a function-call key scoped to the escrow contract. Its pay tool checks the payee and a spend cap in code, outside the model. It also has at least one input defense (for example tagging document content as untrusted, or a classifier). The same swarm should break the naive one and fail on the hardened one. The point for the video: guardrails in code, not in the prompt.

## Non-goals
- Smart contract targets. Stretch only, after every goal above works. If attempted: bounty on a contract, break proven by replaying the exploit on a forked copy of chain state.
- Decentralizing the arena proxy. The arena operator is trusted for routing and transcript logging; the README says so plainly.
- Replaying transcripts inside a TEE. Stretch only.
- Stopping a builder from rigging their own target (for example an agent that can never call `release`). Out of scope; noted in README.
- Mainnet bounties beyond tiny demo amounts. Paying winners in another token via NEAR Intents is a stretch.
- Login or accounts beyond a NEAR account and an API key. Mobile layout beyond "readable".

## Anti-goals (failure even if it technically works)
- The arena attacks an agent whose owner did not register it. Registration must include an ownership check: the endpoint has to echo a one-time token the arena shows the builder.
- The demo depends on LLM luck. There must be a deterministic demo mode the AI judges can run in a few minutes with no API keys and no testnet funds.
- A full-access private key in plain text anywhere: repo, env file committed, logs.
- A README written like a pitch deck.

## Constraints
- Solo, 14 days, ends 14 Nov 23:59 UTC. Leave the last 2 days for README, video, X post, and a fresh-clone test.
- **Demo mode:** one command (for example `make demo`) runs a local NEAR sandbox, deploys the contract, starts the arena, runs scripted attackers against a scripted naive target and a scripted hardened target, and prints the expected result lines. No LLM keys, no testnet.
- **Live mode:** testnet contract, real attackers and targets on NEAR AI Cloud models. Used for the video and the hosted demo.
- Testnet for escrow and bounties. Intents only for the stretch payout feature, on mainnet with tiny amounts.

## How, decided by the user
- AI agents are the main target; smart contracts are a stretch.
- Open arena with a leaderboard; any builder posts, any attacker joins.
- Solo, comfortable with every language, leans Python.
- Success means track prizes in Security and Swarms: narrow scope, polished.
- TreasuryBot is an accounts-payable agent that pays vendor invoices; attacks come through invoices, emails and chat.
- Attackers share partial leads through a lead market (pay to unlock, author paid at unlock), not citations.

## How, default choices (open to override)
- Python for the arena, attackers, and target agents (FastAPI). Rust with near-sdk for the escrow contract.
- Models from NEAR AI Cloud for attackers and live targets (NEAR gives credits; shows NEAR beyond payments).
- One live HTML page served by FastAPI with server-sent events. No React.
- Break types limited to payout and secret-hash, so every win is checked by the contract.
- Fees: prepaid attacker credit in the contract, settled to the poster on close.
- Payouts in NEAR on testnet.
- **Trust boundary:** payout and secret breaks are trustless (checked and paid by the contract). Per-attempt fees are recorded by the arena operator account and settled in batches to the poster; only the operator account may call the fee-settle method. README states this split plainly.
- **Judge machine:** native path, no Docker required. Prebuilt contract `.wasm` committed. `make demo` needs Python 3.11+ and downloads the near-sandbox binary itself. A Docker Compose path is optional extra.

## Left to the builder
- Contract method names, storage layout, events.
- Transcript storage format and where it lives.
- Attacker prompts and strategies within the list in goal 5.
- Lead pricing and how house attackers decide to buy or sell.
- Exact shape of the target HTTP API.
- Fee size, rate limits, number of turns per attempt.
- Which input defense the hardened target uses.
- Page styling.

## Demo video script (about 2 minutes)
1. Builder posts a 5 NEAR bounty on TreasuryBot (naive). Contract shows the escrow.
2. Swarm launches. The live page streams attempts while TreasuryBot pays real vendor invoices. One attacker buys another's lead, sends a fake "bank details changed" email, and lands a payout break in under 2 minutes. The contract pays the attacker; the lead sale and payout show on the leaderboard.
3. Builder opens the private report and reads the winning transcript.
4. Builder posts the same bounty on TreasuryBot (hardened). Same swarm, zero breaks, badge reads "survived N attacks". End with: guardrails in code, not in the prompt.

## Verification
- Contract tests: post bounty; pay to an approved payee works and is not a break; pay to a registered attacker off the list is a break and pays that attacker; pay to an unknown account is refused; only the poster can change the payee list; secret break with right and wrong secret; double payout refused; fees settle to the poster and only the operator can settle; lead unlock pays the author and records the buyer.
- `make demo` from a fresh clone on a clean machine: reproduces the naive break and the hardened survival and prints the expected lines.
- Live run on testnet with NEAR AI Cloud models; record the video from it.
- Dry-run of AI judging: a fresh AI coding agent session follows only the README from a fresh clone and reports what failed.

