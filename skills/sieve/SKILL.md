---
name: sieve
description: Work on the Sieve repository, a grant reviewer for NEAR DAOs whose AI reviews are rebuilt and verified by a NEAR contract. Use when changing the contract, the canonical request, the relayer, the verifier, attestation checks, the red-team harness, the API or the web page, or when deploying or red-teaming Sieve.
license: MIT
---

# Sieve

## Commands

```bash
make setup                                   # venv and editable install
make test                                    # Python unit tests, plus cargo tests when cargo exists
make contract                                # rebuild contract/sieve.wasm after changing contract/src
.venv/bin/python -m pytest -m slow tests/integration   # local sandbox with a real Sputnik DAO
.venv/bin/sieve verify                       # re-check every on-chain review, no key
.venv/bin/sieve redteam report               # re-check and summarize red-team results, no key
.venv/bin/sieve attest                       # needs NEAR_AI_API_KEY
.venv/bin/sieve relay --account <acct> --once            # needs NEAR_AI_API_KEY
```

## Rules every change must keep

1. **One canonical request, three copies.** `sieve/request.py`, `contract/src/request.rs` and `buildRequest` in `web/app.js` must produce the same bytes. If you change the layout, change all three. Then:
   - re-record `tests/fixtures/signed_review.json` with `pytest -m live tests/live`;
   - run `cargo test`, whose `request_matches_python_fixture` test must pass.
2. **Parsing rules match.** `sieve/nearai.py::parse_review` and `contract/src/review.rs::parse` accept and reject the same answers: one optional code fence, an integer score from 0 to 10, and a list of string flags.
3. **The contract trusts only registered model keys.** Never add a path where the relayer, the API or the owner can set a score.
4. **Errors keep their message in release wasm.** Use `ensure!` and `.or_fail(...)`, not `require!` or `expect`.
5. **No faked results.** Demo and recorded results come from real testnet and real NEAR AI Cloud calls; unit tests may use test keys.
6. **Secrets come from the environment only.** That means `NEAR_AI_API_KEY` and `SIEVE_ACCOUNT_KEY`, or `~/.near-credentials/testnet/`. They are never written to the repository, logs or transcripts.

## Red-teaming Sieve

Add an attack to `sieve/redteam/attacks.py` (a function from a clean body to an injected body that keeps the clean text), add it to `ATTACKS`, and rerun `sieve redteam run`. The `prompt-injection-test` skill lists technique families worth trying.

To test the live system, submit to the current honeypot round in `deployments/testnet.json`. A passing median with no injection flag wins the bounty.
