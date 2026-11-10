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
| Applicant resamples until a model gives a high score | For the review window (one hour in the current rounds) any relayer may post a lower signed score for the same slot, and the lowest wins. The project's relayer re-reviews every slot holding a passing score on each pass and posts its own score when it is lower |
| One model is fooled | The median of three different models decides; any `injection` flag blocks a pass |
| Unregistered or stale model key | Keys are registered per model with an expiry; the contract rejects others |
| DAO call fails | The bond is returned to the round and `finalize` can be retried; nothing is marked final |
| One signature filling two slots | A round's models must be distinct; each slot's request names its model |
| Review data draining the contract | Storage for every review slot is reserved and paid at submit; only known flags are stored |
| Padding a proposal with plausible detail to stretch the score | Not prevented by the rubric. A checklist the contract counts was tried and measured: an attacker that retries still passed 12 of 15, and honest proposals passed only 3 of 20, so the demo round uses the 0-to-10 rubric. What limits the damage is the 0.2 NEAR newcomer tranche, evidence review before each later tranche, and the DAO vote |
| Fake track record ("our last grant reached 5,000 users") | The applicant's record (first seen, earlier proposals, passed, milestones delivered) is written into every request by the contract; the rubric tells the model to give in-proposal claims about the past no weight, and the track-record check can only be ticked from the contract's record |
| A proposal that only looks good on paper | Newcomers get a small first tranche; each later tranche needs delivery evidence that passes its own three-model review, opened only after the contract confirms with the DAO that members approved the previous payout |
| Double payout | `finalize` runs once per proposal; the honeypot round closes when its bounty is paid |

## What is checked off chain, and by whom

- **Attestation.** Before registering a key, the owner checks the model's attestation report: nonce echo, key bound in the TDX quote's report data, GPU evidence nonce, and the Intel quote signature (`dcap-qvl`). Anyone can rerun `sieve attest` and compare the keys with `deployments/testnet.json` and the contract's `get_signer`.
- **Re-verification.** `sieve verify` and the web page recheck every review from public data.

## Known limits

- All replicas of a model share one signing key (NEAR AI Cloud documents this), so a signature identifies the model's enclave image, not one machine.
- A `provider_tee` signature is not bound to the gateway's TLS evidence (NEAR AI Cloud documents this as well).
- TEEs do not resist physical attacks. Published attacks such as TEE.fail (2025) forge attestations with hardware access to the server.
- The contract trusts the owner to register the right keys. Key registration is public, and anyone can audit it with `sieve attest`.
- Delivery evidence is judged as text. The models cannot open links, so evidence is checked for being specific and checkable (commit hashes, contract accounts, transaction ids) and DAO members check it before voting. Making milestones on-chain predicates the contract checks itself (a code hash, a call count) is the next step.
- Prompt injection is reduced, not solved. `results/redteam/REPORT.md` reports measured rates, including the deployed three-model median.
- Duplicate and sybil signals are advisory and can be gamed. NEAR accounts are cheap to create.
- The attestation check compares the key binding, nonces and Intel's signature on the TDX quote, but not the enclave's measurements (MRTD, RTMR, compose hash) against a published reference, and it checks only that the NVIDIA GPU evidence echoes our nonce. Any genuine TDX machine that binds the key would pass. Registration refuses keys whose Intel quote could not be verified.
- An applicant can try the reverse of cherry-picking: posting a low signed score or an `injection` flag on a rival's good proposal. That is possible only if a model really gave that answer to the pinned request, and lowest-wins accepts it by design. Reviews are public, so members voting can see it.
- If no honest relayer runs during a review window, a resampled score stands. The project's own relayer runs every ten minutes, and the current rounds' window is one hour.
