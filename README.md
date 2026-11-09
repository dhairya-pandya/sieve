# Sieve

Sieve is a grant reviewer for NEAR DAOs. Three AI models running in NEAR AI Cloud's trusted execution environments review each proposal against a rubric stored on chain. A NEAR contract rebuilds the exact prompt, checks each model's signature, takes the median score, and files a payout proposal on the community's Sputnik DAO for members to vote on. Before a round opens, an attacker swarm tries to manipulate the reviewer with injected proposals, and the measured results are published.

Work in progress for the NEAR Hackathon (November 2026).

## License

MIT, see `LICENSE`.
