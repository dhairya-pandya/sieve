# Sieve threat model

## Assets

- The DAO treasury. Sieve never holds it; it can only add Transfer proposals that members vote on.
- The honeypot bounty, held by the Sieve contract.
- The round's DAO proposal bonds, held by the Sieve contract.
- The integrity of scores, which members rely on when they vote.

## Actors

- **Applicant:** submits proposals and may try to manipulate the reviewer.
- **Relayer:** anyone. It sends proposals to the models and posts signed answers.
- **Contract owner:** registers model signing keys.
- **NEAR AI Cloud:** runs the models in TEEs and signs their answers.
- **DAO members:** vote on the proposals Sieve files.

## What is checked on chain

| Threat | Defense |
|---|---|
| Operator or relayer changes the rubric or prompt | The contract builds the request from the round's stored prompt and the stored proposal, then checks the signature over its hash |
| Forged or edited score | The signature covers the hash of the exact response bytes; the contract parses the score from them |
| Signed answer reused on another proposal, round or slot | Round id, proposal id, model and a contract-chosen seed are inside the signed request |
| Applicant resamples until a model gives a high score | For the review window (one hour in the current rounds) any relayer may post a lower signed score for the same slot, and the lowest wins; an honest relayer always posts |
| One model is fooled | The median of three different models decides; any `injection` flag blocks a pass |
| Unregistered or stale model key | Keys are registered per model with an expiry; the contract rejects others |
| DAO call fails | The bond is returned to the round and `finalize` can be retried; nothing is marked final |
| Double payout | `finalize` runs once per proposal; the honeypot round closes when its bounty is paid |

## What is checked off chain, and by whom

- **Attestation.** Before registering a key, the owner checks the model's attestation report: nonce echo, key bound in the TDX quote's report data, GPU evidence nonce, and the Intel quote signature (`dcap-qvl`). Anyone can rerun `sieve attest` and compare the keys with `deployments/testnet.json` and the contract's `get_signer`.
- **Re-verification.** `sieve verify` and the web page recheck every review from public data.

## Known limits

- All replicas of a model share one signing key (NEAR AI Cloud documents this), so a signature identifies the model's enclave image, not one machine.
- A `provider_tee` signature is not bound to the gateway's TLS evidence (NEAR AI Cloud documents this as well).
- TEEs do not resist physical attacks. Published attacks such as TEE.fail (2025) forge attestations with hardware access to the server.
- The contract trusts the owner to register the right keys. Key registration is public, and anyone can audit it with `sieve attest`.
- Prompt injection is reduced, not solved. `results/redteam/REPORT.md` reports measured rates, including the deployed three-model median.
- Duplicate and sybil signals are advisory and can be gamed. NEAR accounts are cheap to create.
- If no honest relayer runs during a review window, a resampled score stands. The project's own relayer runs every ten minutes, and the current rounds' window is one hour.
