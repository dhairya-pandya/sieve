use near_sdk::json_types::{Base64VecU8, U128};
use near_sdk::store::{LookupMap, Vector};
use near_sdk::{env, near, AccountId, Gas, NearToken, PanicOnDefault, Promise, PromiseOrValue};

/// Like `require!`, but keeps the message in release builds so callers see why a call failed.
macro_rules! ensure {
    ($cond:expr, $msg:expr) => {
        if !$cond {
            near_sdk::env::panic_str(&$msg)
        }
    };
}

trait OrFail<T> {
    fn or_fail(self, msg: &str) -> T;
}

impl<T> OrFail<T> for Option<T> {
    fn or_fail(self, msg: &str) -> T {
        self.unwrap_or_else(|| env::panic_str(msg))
    }
}

mod request;
mod review;
mod finalize;

pub const MAX_TITLE: usize = 200;
pub const MAX_BODY: usize = 8_000;
pub const MAX_MODELS: usize = 5;
/// Storage reserved per review slot at submit time, so reviews never spend the contract's own balance.
pub const SLOT_RESERVE_BYTES: u64 = 300;
/// Only these flags are stored; anything else a model emits is ignored.
pub const KNOWN_FLAGS: [&str; 4] = ["injection", "duplicate", "off_topic", "low_effort"];

#[near(serializers = [borsh, json])]
#[derive(Clone, Debug, PartialEq)]
pub enum RoundKind {
    Grant,
    Honeypot,
}

#[near(serializers = [borsh, json])]
#[derive(Clone, Debug)]
pub struct Signer {
    pub model: String,
    pub expires_ms: u64,
}

#[near(serializers = [borsh, json])]
#[derive(Clone, Debug)]
pub struct Round {
    pub kind: RoundKind,
    pub creator: AccountId,
    pub dao: AccountId,
    pub system: String,
    pub models: Vec<String>,
    pub threshold: u8,
    pub tranche: U128,
    pub dao_bond: U128,
    pub window_ms: u64,
    pub bounty: U128,
    pub bonds: U128,
    pub open: bool,
}

#[near(serializers = [borsh, json])]
#[derive(Clone, Debug)]
pub struct Slot {
    pub score: u8,
    pub flags: Vec<String>,
    pub response_hash: String,
}

#[near(serializers = [borsh, json])]
#[derive(Clone, Debug, PartialEq)]
pub struct Outcome {
    pub median: u8,
    pub passed: bool,
    pub dao_proposal_id: Option<u64>,
    pub paid: Option<U128>,
}

#[near(serializers = [borsh, json])]
#[derive(Clone, Debug)]
pub struct Proposal {
    pub round_id: u64,
    pub author: AccountId,
    pub title: String,
    pub body: String,
    pub seed: u64,
    pub submitted_ms: u64,
    pub slots: Vec<Option<Slot>>,
    pub finalized: bool,
    pub pending: bool,
    pub outcome: Option<Outcome>,
}

#[near(contract_state)]
#[derive(PanicOnDefault)]
pub struct Sieve {
    owner: AccountId,
    signers: LookupMap<String, Signer>,
    rounds: Vector<Round>,
    proposals: Vector<Proposal>,
}

#[near]
impl Sieve {
    #[init]
    pub fn new(owner: AccountId) -> Self {
        Self {
            owner,
            signers: LookupMap::new(b"s"),
            rounds: Vector::new(b"r"),
            proposals: Vector::new(b"p"),
        }
    }

    /// Register a NEAR AI Cloud model signing key (hex ed25519) after checking its attestation off chain.
    pub fn register_signer(&mut self, public_key_hex: String, model: String, expires_ms: u64) {
        ensure!(env::predecessor_account_id() == self.owner, "only the owner registers signers");
        ensure!(public_key_hex.len() == 64 && public_key_hex.bytes().all(|b| b.is_ascii_hexdigit()), "key must be 32 bytes hex");
        self.signers.insert(public_key_hex.to_ascii_lowercase(), Signer { model, expires_ms });
    }

    /// Open a round. The attached deposit is the honeypot bounty, or the DAO proposal bonds for a grant round.
    #[payable]
    pub fn create_round(
        &mut self,
        kind: RoundKind,
        dao: AccountId,
        system: String,
        models: Vec<String>,
        threshold: u8,
        tranche: U128,
        dao_bond: U128,
        window_ms: u64,
    ) -> u64 {
        ensure!(!models.is_empty() && models.len() <= MAX_MODELS, "a round needs 1 to 5 models");
        ensure!(threshold <= 10, "threshold is a score from 0 to 10");
        let mut distinct = models.clone();
        distinct.sort();
        distinct.dedup();
        ensure!(distinct.len() == models.len(), "models must be distinct");
        ensure!(window_ms > 0, "window must be positive");
        let deposit = U128(env::attached_deposit().as_yoctonear());
        let (bounty, bonds) = match kind {
            RoundKind::Honeypot => (deposit, U128(0)),
            RoundKind::Grant => (U128(0), deposit),
        };
        self.rounds.push(Round {
            kind,
            creator: env::predecessor_account_id(),
            dao,
            system,
            models,
            threshold,
            tranche,
            dao_bond,
            window_ms,
            bounty,
            bonds,
            open: true,
        });
        self.rounds.len() as u64 - 1
    }

    /// Submit a proposal. The attached deposit must cover its storage; any excess is refunded.
    #[payable]
    pub fn submit(&mut self, round_id: u64, title: String, body: String) -> u64 {
        ensure!(title.len() <= MAX_TITLE, "title too long");
        ensure!(body.len() <= MAX_BODY, "body too long");
        let round = self.rounds.get(round_id as u32).or_fail("no such round");
        ensure!(round.open, "round is closed");
        let slots = vec![None; round.models.len()];
        let seed_bytes: [u8; 4] = env::random_seed()[..4].try_into().unwrap();
        let before = env::storage_usage();
        self.proposals.push(Proposal {
            round_id,
            author: env::predecessor_account_id(),
            title,
            body,
            seed: u32::from_le_bytes(seed_bytes) as u64,
            submitted_ms: env::block_timestamp_ms(),
            slots,
            finalized: false,
            pending: false,
            outcome: None,
        });
        self.proposals.flush();
        let reserved = SLOT_RESERVE_BYTES * round.models.len() as u64;
        let cost = env::storage_byte_cost().saturating_mul((env::storage_usage() - before + reserved) as u128);
        let attached = env::attached_deposit();
        ensure!(attached >= cost, format!("storage deposit of {} yoctoNEAR required", cost.as_yoctonear()));
        let refund = attached.saturating_sub(cost);
        if refund > NearToken::from_yoctonear(0) {
            let _ = Promise::new(env::predecessor_account_id()).transfer(refund);
        }
        self.proposals.len() as u64 - 1
    }

    /// Post a TEE-signed review for one slot. Anyone may call; the contract trusts only registered model keys.
    /// Within the window the lowest valid score for a slot wins. Returns the slot's score after this review.
    pub fn post_review(&mut self, proposal_id: u64, slot: u8, response: Base64VecU8, signature_hex: String, public_key_hex: String) -> u8 {
        let response: Vec<u8> = response.into();
        ensure!(response.len() <= review::MAX_RESPONSE, "response too large");
        let p = self.proposals.get(proposal_id as u32).or_fail("no such proposal").clone();
        let round = self.rounds.get(p.round_id as u32).or_fail("no such round").clone();
        let model = round.models.get(slot as usize).or_fail("no such slot").clone();
        let now = env::block_timestamp_ms();
        ensure!(now <= p.submitted_ms + round.window_ms, "review window closed");
        let pk_hex = public_key_hex.to_ascii_lowercase();
        let signer = self.signers.get(&pk_hex).filter(|s| s.model == model).or_fail("key is not registered for this model");
        ensure!(now < signer.expires_ms, "signer key expired");
        let request = self.request_bytes(proposal_id, slot);
        let response_hash = review::hex(&env::sha256(&response));
        let text = format!("{model}:{}:{response_hash}", review::hex(&env::sha256(&request)));
        let sig = review::unhex::<64>(&signature_hex.to_ascii_lowercase()).or_fail("bad signature");
        let pk = review::unhex::<32>(&pk_hex).or_fail("bad public key");
        ensure!(env::ed25519_verify(&sig, text.as_bytes(), &pk), "bad signature");
        let mut parsed = review::parse(&response).unwrap_or_else(|e| env::panic_str(e));
        let mut kept_flags: Vec<String> = Vec::new();
        for f in parsed.flags.iter().filter(|f| KNOWN_FLAGS.contains(&f.as_str())) {
            if !kept_flags.contains(f) {
                kept_flags.push(f.clone());
            }
        }
        parsed.flags = kept_flags;
        let entry = &mut self.proposals.get_mut(proposal_id as u32).unwrap().slots[slot as usize];
        if entry.as_ref().map_or(true, |s| parsed.score < s.score) {
            *entry = Some(Slot { score: parsed.score, flags: parsed.flags.clone(), response_hash });
        }
        let kept = entry.as_ref().unwrap().score;
        let event = near_sdk::serde_json::json!({
            "standard": "sieve", "version": "1.0.0", "event": "review",
            "data": [{
                "proposal_id": proposal_id, "slot": slot, "model": model, "score": parsed.score,
                "flags": parsed.flags, "public_key": pk_hex, "signature": signature_hex.to_ascii_lowercase(),
                "response": near_sdk::base64::Engine::encode(&near_sdk::base64::engine::general_purpose::STANDARD, &response),
            }]
        });
        env::log_str(&format!("EVENT_JSON:{event}"));
        kept
    }

    /// Add to a round's DAO proposal bonds (grant round) or bounty (honeypot round).
    #[payable]
    pub fn fund_round(&mut self, round_id: u64) {
        let amount = env::attached_deposit().as_yoctonear();
        let r = self.rounds.get_mut(round_id as u32).or_fail("no such round");
        ensure!(r.open, "round is closed");
        match r.kind {
            RoundKind::Honeypot => r.bounty = U128(r.bounty.0 + amount),
            RoundKind::Grant => r.bonds = U128(r.bonds.0 + amount),
        }
    }

    /// Close a round and return its unspent bounty and bonds to the creator. Proposals already
    /// submitted can still be reviewed and finalized; passing ones file to the DAO only while bonds remain.
    pub fn close_round(&mut self, round_id: u64) -> U128 {
        let r = self.rounds.get_mut(round_id as u32).or_fail("no such round");
        ensure!(env::predecessor_account_id() == r.creator, "only the round creator can close it");
        ensure!(r.open, "round is closed");
        let refund = r.bounty.0 + r.bonds.0;
        r.open = false;
        r.bounty = U128(0);
        r.bonds = U128(0);
        if refund > 0 {
            let _ = Promise::new(r.creator.clone()).transfer(NearToken::from_yoctonear(refund));
        }
        U128(refund)
    }

    /// Settle a proposal once its review window has closed. A passing grant proposal files a Transfer
    /// proposal for the first tranche on the round's Sputnik DAO; a passing honeypot proposal wins the bounty.
    pub fn finalize(&mut self, proposal_id: u64) -> PromiseOrValue<Outcome> {
        let p = self.proposals.get(proposal_id as u32).or_fail("no such proposal").clone();
        ensure!(!p.finalized, "already finalized");
        ensure!(!p.pending, "DAO filing in progress");
        let round = self.rounds.get(p.round_id as u32).or_fail("no such round").clone();
        ensure!(env::block_timestamp_ms() > p.submitted_ms + round.window_ms, "review window still open");
        let (median, filled) = finalize::median(&p.slots).unwrap_or((0, 0));
        ensure!(filled >= round.models.len().min(2), "needs at least 2 reviews");
        let passed = median >= round.threshold && !finalize::flagged_injection(&p.slots);
        let mut outcome = Outcome { median, passed, dao_proposal_id: None, paid: None };
        match (passed, &round.kind) {
            (true, RoundKind::Honeypot) if round.bounty.0 > 0 => {
                outcome.paid = Some(round.bounty);
                let r = self.rounds.get_mut(p.round_id as u32).unwrap();
                r.bounty = U128(0);
                r.open = false;
                let _ = Promise::new(p.author.clone()).transfer(NearToken::from_yoctonear(round.bounty.0));
            }
            (true, RoundKind::Grant) => {
                ensure!(round.bonds.0 >= round.dao_bond.0, "round has no bonds left for DAO proposals");
                self.rounds.get_mut(p.round_id as u32).unwrap().bonds = U128(round.bonds.0 - round.dao_bond.0);
                let prop = self.proposals.get_mut(proposal_id as u32).unwrap();
                prop.pending = true;
                prop.outcome = Some(outcome);
                let args = near_sdk::serde_json::json!({"proposal": {
                    "description": format!("Sieve round {} proposal {}: {}", p.round_id, proposal_id, p.title),
                    "kind": {"Transfer": {"token_id": "", "receiver_id": p.author, "amount": round.tranche}},
                }});
                return PromiseOrValue::Promise(
                    Promise::new(round.dao.clone())
                        .function_call("add_proposal".to_string(), args.to_string().into_bytes(),
                            NearToken::from_yoctonear(round.dao_bond.0), Gas::from_tgas(30))
                        .then(Promise::new(env::current_account_id()).function_call(
                            "on_dao_proposal".to_string(),
                            near_sdk::serde_json::json!({"proposal_id": proposal_id}).to_string().into_bytes(),
                            NearToken::from_yoctonear(0), Gas::from_tgas(15))),
                );
            }
            _ => {}
        }
        let prop = self.proposals.get_mut(proposal_id as u32).unwrap();
        prop.finalized = true;
        prop.outcome = Some(outcome.clone());
        PromiseOrValue::Value(outcome)
    }

    /// Result of the DAO's add_proposal. On failure the bond (refunded by the runtime) goes back to the round.
    #[private]
    pub fn on_dao_proposal(&mut self, proposal_id: u64) -> Outcome {
        let id = env::promise_result_checked(0, 64)
            .ok()
            .and_then(|v| near_sdk::serde_json::from_slice::<u64>(&v).ok());
        let round_id = self.proposals.get(proposal_id as u32).or_fail("no such proposal").round_id;
        let p = self.proposals.get_mut(proposal_id as u32).unwrap();
        p.pending = false;
        let mut outcome = p.outcome.clone().or_fail("outcome set before filing");
        match id {
            Some(id) => {
                p.finalized = true;
                outcome.dao_proposal_id = Some(id);
                p.outcome = Some(outcome.clone());
            }
            None => {
                p.outcome = None;
                let r = self.rounds.get_mut(round_id as u32).unwrap();
                if r.open {
                    r.bonds = U128(r.bonds.0 + r.dao_bond.0);
                } else if r.dao_bond.0 > 0 {
                    let _ = Promise::new(r.creator.clone()).transfer(NearToken::from_yoctonear(r.dao_bond.0));
                }
            }
        }
        outcome
    }

    /// The exact request bytes a reviewer must send to NEAR AI Cloud for this proposal and slot.
    pub fn review_request(&self, proposal_id: u64, slot: u8) -> Base64VecU8 {
        Base64VecU8(self.request_bytes(proposal_id, slot))
    }

    pub fn get_signer(&self, public_key_hex: String) -> Option<Signer> {
        self.signers.get(&public_key_hex.to_ascii_lowercase()).cloned()
    }

    pub fn get_round(&self, round_id: u64) -> Option<Round> {
        self.rounds.get(round_id as u32).cloned()
    }

    pub fn get_proposal(&self, proposal_id: u64) -> Option<Proposal> {
        self.proposals.get(proposal_id as u32).cloned()
    }

    pub fn round_count(&self) -> u64 {
        self.rounds.len() as u64
    }

    /// Proposals of a round with ids from `from`, at most `limit` of them.
    pub fn list_proposals(&self, round_id: u64, from: u64, limit: u64) -> Vec<(u64, Proposal)> {
        (from..self.proposals.len() as u64)
            .filter_map(|id| self.proposals.get(id as u32).map(|p| (id, p)))
            .filter(|(_, p)| p.round_id == round_id)
            .take(limit as usize)
            .map(|(id, p)| (id, p.clone()))
            .collect()
    }
}

impl Sieve {
    fn request_bytes(&self, proposal_id: u64, slot: u8) -> Vec<u8> {
        let p = self.proposals.get(proposal_id as u32).or_fail("no such proposal");
        let round = self.rounds.get(p.round_id as u32).or_fail("no such round");
        let model = round.models.get(slot as usize).or_fail("no such slot");
        request::build(model, &round.system, p.round_id, proposal_id, &p.title, &p.body, p.seed)
    }

    #[cfg(test)]
    pub(crate) fn set_seed_for_test(&mut self, proposal_id: u64, seed: u64) {
        self.proposals.get_mut(proposal_id as u32).unwrap().seed = seed;
    }
}

#[cfg(test)]
mod tests;
#[cfg(test)]
mod review_tests;
#[cfg(test)]
mod finalize_tests;
#[cfg(test)]
mod fix_tests;
