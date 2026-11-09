# Agent skills

Skills in the open [Agent Skills](https://agentskills.io) format (a folder with a `SKILL.md`). Any coding or attacker agent that reads this format can load them to work on Sieve or to red-team its reviewer.

| Skill | Use it for |
|---|---|
| `sieve/` | Working on this repository: layout, tests, and the rules every change must keep |
| `near-smart-contracts/` | Writing and reviewing the Sieve contract in `contract/` (near-sdk 5.x) |
| `near-contract-sim/` | Testing the Sieve contract in-process with near-contract-sim, including fault and audit harnesses |
| `fastapi/` | Changing the Sieve API service |
| `prompt-injection-test/` | Planning prompt-injection attacks against a target, by intent, technique and evasion |
| `promptfoo-provider-setup/`, `promptfoo-redteam-setup/`, `promptfoo-redteam-run/` | Pointing a promptfoo red-team scan at the reviewer and reading attack success rates |

Only `sieve/` was written for this project. The others are copied unchanged from their upstream repositories, except that per-tool `agents/` manifest folders were left out and the prompt-injection play was moved next to its `SKILL.md` so its relative link resolves.

## Sources and licenses

| Skill | Source | Commit | License | Notice |
|---|---|---|---|---|
| `near-smart-contracts` | https://github.com/near/agent-skills, `skills/near-smart-contracts` | `cb32b6af195e636c1e9c2efe2ea75a6d85b6b67b` | MIT (declared in the skill's frontmatter; the upstream repository has no LICENSE file) | Author: NEAR |
| `near-contract-sim` | https://github.com/near/near-contract-sim, `skills/near-contract-sim` | `059cfa18900cacad2d9b86b1e989f476b4c6591a` | MIT OR Apache-2.0 | Copyright (c) 2026 NEAR. See `LICENSES/near-contract-sim-MIT.txt` and `LICENSES/near-contract-sim-APACHE-2.0.txt` |
| `fastapi` | https://github.com/fastapi/fastapi, `fastapi/.agents/skills/fastapi` | `ba47d6d71b3e806900c8471f2f661781b8c43ec4` | MIT | Copyright (c) 2018 Sebastián Ramírez. See `LICENSES/fastapi-MIT.txt` |
| `prompt-injection-test` | https://github.com/OWASP/secure-agent-playbook, `plugins/ai-security-skills/skills/prompt-injection-test` and `plugins/ai-security-skills/plays/prompt-injection-testing.md` | `65d4efd2cd0b081d52101e9708792b944e4ddebb` | CC-BY-4.0 | OWASP Secure Agent Playbook contributors. Based on the Arcanum Prompt Injection Taxonomy by Jason Haddix, Arcanum Information Security (https://github.com/Arcanum-Sec/arc_pi_taxonomy), CC BY 4.0. Change made: the play file moved from `plays/` at the plugin root to `prompt-injection-test/plays/`. See `LICENSES/owasp-secure-agent-playbook-CC-BY-4.0.md` |
| `promptfoo-provider-setup`, `promptfoo-redteam-setup`, `promptfoo-redteam-run` | https://github.com/promptfoo/promptfoo, `plugins/promptfoo/skills/` | `b76f5a1b7ee2b2dcbb377dfcd008b6f6b255ebfa` | MIT | Copyright (c) Promptfoo 2025. See `LICENSES/promptfoo-MIT.txt`. The bundled `js-yaml.mjs` keeps its own MIT notice in `promptfoo-provider-setup/scripts/vendor/LICENSE` |

The `sieve` skill is under the repository's MIT license.
