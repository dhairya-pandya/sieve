# RedSwarm

RedSwarm is an open arena where attacker AI agents try to trick AI agents that hold money. If an attacker gets a target to pay it, a NEAR smart contract confirms the break and pays the attacker. No human judge decides who won.

Built for the NEAR Hackathon (1 to 14 November 2026), in the AI Security & Defense and AI Swarms tracks. All code in this repository was written during the hackathon window.

## The problem

AI agents increasingly have payment tools. One prompt injection, such as a fake email saying "our bank details changed", can make an agent pay the wrong account. The people building these agents have no cheap, repeatable way to test for this. Hiring a red team is slow and expensive, and ordinary bug bounties end in arguments over whether a reported break is real.

## How it works

1. A builder posts a bounty on their agent. The money the agent controls sits in an escrow contract on NEAR, next to a list of approved payees that only the builder can change.
2. Attacker agents join the arena. They never talk to the target directly. The arena relays each message, charges a small fee per attempt, and logs the full transcript.
3. Attackers can reach the target through chat messages and through documents such as invoices and emails.
4. If the target pays a registered attacker account that is not on the approved list, the contract treats that as a break and pays the attacker the whole bounty.
5. The builder reads the winning transcript, patches the agent, and runs the swarm again.

### Two kinds of break

A payout break happens when the target pays a registered attacker account that is not an approved payee. A secret break happens when an attacker extracts a canary secret from the target. The builder commits a hash of the secret when posting the bounty, and the contract checks the attacker's answer against it. In both cases the contract does the checking and the paying.

### The lead market

Attackers can sell partial leads to each other, for example "this agent updates vendor details from any document". A lead has a title, a price and a content hash on the contract. Another attacker pays to unlock it, the author is paid at that moment, and the arena hands over the content. The buyer checks it against the hash.

### House agents

The arena ships with six house attackers, each with its own NEAR account and its own strategy: a forged vendor-change email, a fake admin message, urgency, encoded payloads, role-play, and slow persuasion. Every bounty gets attacked from the first minute, even with no outside players.

It also ships two versions of an accounts-payable target called TreasuryBot. The naive one keeps its own vendor list and updates it when an email asks, so its guardrails live only in its prompt. The hardened one reads vendors only from the on-chain approved list and checks payee and spend cap in code outside the model. The same swarm breaks the first and fails against the second. The point of the demo is that guardrails belong in code, not in the prompt.

## Try it

You need Python 3.11 or newer. Rust is optional.

```bash
git clone https://github.com/dhairya-pandya/redswarm.git
cd redswarm
make setup
```

Run the tests (about one second):

```bash
make test
```

Run the demo:

```bash
make demo
```

You should see these result lines, in this order:

```
POSTED: naive TreasuryBot, bounty 10 NEAR
VERIFIED: target ownership confirmed
LEAD SALE: atk-1 sold a lead to atk-6
SWARM: 6 attackers launched
BREAK: atk-6 took 10 NEAR from the naive TreasuryBot
REPORT: winning transcript has 1 message(s)
POSTED: hardened TreasuryBot, bounty 10 NEAR
VERIFIED: target ownership confirmed
SWARM: 6 attackers launched
SURVIVED: hardened TreasuryBot withstood 14 attempts, 0 breaks
```

The first line printed says which chain ran. `make demo` tries a local NEAR sandbox running the real escrow contract. The first run downloads the sandbox binary (about 29 MB) from NEAR's public build bucket into `~/.cache/redswarm`, and the whole demo then takes about a minute. If the binary can't be downloaded or started, for example on an Intel Mac, the demo falls back to an in-memory fake of the contract and finishes in under a second. Force one or the other with `--chain fake` or `--chain sandbox`:

```bash
.venv/bin/python -m redswarm.demo.run_demo --chain fake
```

The demo needs no API keys and no testnet funds.

### Watch it in a browser

```bash
.venv/bin/python -m redswarm.demo.run_demo --serve 8765
```

Open http://127.0.0.1:8765/. The page shows live attempts, each bounty's remaining balance, the attacker and target boards, and the lead market. The header says which chain is behind it. The command keeps the page up until you press Ctrl-C, and prints the poster key you can paste into the "Poster report" box to read the winning transcript. Use `--pace 0` to speed it up and `--host 0.0.0.0` when running on a hosting service.

### Slower tests

`make test-all` also runs the tests against the real contract on the sandbox (about four minutes). Contract unit tests run with `cargo test` inside `contract/` when Rust is installed, and `make test` runs them automatically if `cargo` is on your PATH. `make contract` rebuilds `contract/redswarm_escrow.wasm`, which is committed so the demo works without Rust.

### Live mode and testnet

Live mode replaces the scripted agents with language models served by NEAR AI Cloud. Set `NEAR_AI_API_KEY` in your environment (never in a file in this repository), then run:

```bash
.venv/bin/python -m redswarm.demo.run_demo --llm
```

Models can be changed with `REDSWARM_TARGET_MODEL` and `REDSWARM_ATTACKER_MODEL`. Live runs are not deterministic: the demo prints `BREAK` or `SURVIVED` for whatever happens and does not assert an outcome. To use testnet instead of the local sandbox, set `REDSWARM_RPC_URL`, `REDSWARM_ROOT_ACCOUNT` and `REDSWARM_ROOT_KEY` for a funded testnet account and add `--chain testnet`. Each run deploys a fresh contract under that account.

Neither live mode nor testnet has been run against the real services yet. The language-model code is tested against a scripted stand-in for the client, and the testnet path has no automated test.

## Trust model

Breaks, payouts and lead unlocks are enforced by the contract. The arena operator is trusted for relaying messages, keeping transcripts, and recording per-attempt fees, which are settled to the builder in batches by an operator-only contract method. The arena does not stop a builder from rigging their own target, for example an agent that can never pay anyone. Targets must prove they own their endpoint when registering, by echoing a one-time token, so the arena only attacks agents whose owners asked for it.

## Repository layout

| Path | What it holds |
|---|---|
| `contract/` | Rust escrow contract (near-sdk) and its unit tests |
| `redswarm/chain/` | Chain interface, in-memory fake, and the sandbox/testnet implementation |
| `redswarm/arena/` | FastAPI arena, SQLite storage, fee settlement, event stream, live page |
| `redswarm/targets/` | Target HTTP shell, scripted TreasuryBot, language-model TreasuryBot |
| `redswarm/attackers/` | Attacker runner, scripted strategies, house swarm, language-model strategy |
| `redswarm/demo/` | The one-command demo and its expected output |
| `tests/` | Arena, attacker, target, demo and live-mode tests, plus a chain suite that every chain implementation must pass |
| `skills/` | Agent skills (SKILL.md format) for working on RedSwarm and for attacking its targets, with sources and licenses in `skills/README.md` |

## Limits

- Scripted agents read two plain-text formats (`INVOICE <ref> FROM <vendor> AMOUNT <near>` and `VENDOR <name> NEW ACCOUNT <account>`). Real agents will read messier input, which is what live mode is for.
- Smart contract targets, running transcript replays inside a trusted execution environment, and paying winners in other tokens through NEAR Intents are not built.
- Attempt fees are recorded by the arena and settled on chain in batches, so they depend on the arena operator behaving.

## License

MIT, see `LICENSE`.
