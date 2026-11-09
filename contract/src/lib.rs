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
pub const MAX_EVIDENCE: usize = 4_000;
const DAY_MS: u64 = 86_400_000;
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
    /// Rubric for milestone reviews; empty means the round pays a single tranche.
    pub milestone_system: String,
    /// First tranche for applicants who have never delivered a milestone; `tranche` for everyone else.
    pub newcomer_tranche: U128,
    /// Payouts per proposal: the first after the proposal passes, one more per delivered milestone.
    pub tranches: u8,
    pub proposal_count: u64,
}

/// What the contract knows about an applicant. A snapshot goes into every review request, so the
/// reviewer sees a track record the applicant cannot write.
#[near(serializers = [borsh, json])]
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Record {
    pub days: u64,
    pub submitted: u32,
    pub passed: u32,
    pub delivered: u32,
}

#[near(serializers = [borsh, json])]
#[derive(Clone, Debug, Default)]
pub struct History {
    pub first_seen_ms: u64,
    pub submitted: u32,
    pub passed: u32,
    pub delivered: u32,
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
    /// Tranche filed on the DAO for this stage, if any.
    pub amount: U128,
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
    /// Applicant record when this stage opened.
    pub record: Record,
    /// 0 is the proposal itself; n is the review of milestone n's delivery evidence.
    pub stage: u8,
    pub evidence: Option<String>,
    /// DAO proposal ids of the tranches filed so far, in order.
    pub dao_proposal_ids: Vec<u64>,
    pub completed: bool,
    /// Seed, record and evidence of each earlier stage, so its reviews can still be rebuilt and checked.
    pub past: Vec<PastStage>,
}

#[near(serializers = [borsh, json])]
#[derive(Clone, Debug)]
pub struct PastStage {
    pub seed: u64,
    pub record: Record,
    pub evidence: Option<String>,
}

#[near(contract_state)]
#[derive(PanicOnDefault)]
pub struct Sieve {
    owner: AccountId,
    signers: LookupMap<String, Signer>,
    rounds: Vector<Round>,
    proposals: Vector<Proposal>,
    history: LookupMap<AccountId, History>,
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
            history: LookupMap::new(b"h"),
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
            milestone_system: String::new(),
            newcomer_tranche: tranche,
            tranches: 1,
            proposal_count: 0,
        });
        self.rounds.len() as u64 - 1
    }

    /// Turn on milestone payouts for a grant round: `tranches` payouts per proposal, a smaller first tranche
    /// for applicants with no delivered milestone, and the rubric milestone evidence is reviewed against.
    /// Only the creator, and only before the first proposal, so rules never change under applicants.
    pub fn set_milestones(&mut self, round_id: u64, milestone_system: String, newcomer_tranche: U128, tranches: u8) {
        let r = self.rounds.get_mut(round_id as u32).or_fail("no such round");
        ensure!(env::predecessor_account_id() == r.creator, "only the round creator can set milestones");
        ensure!(r.proposal_count == 0, "rules cannot change after the first proposal");
        ensure!(r.kind == RoundKind::Grant, "only grant rounds have milestones");
        ensure!((1..=10).contains(&tranches), "tranches must be 1 to 10");
        ensure!(newcomer_tranche.0 <= r.tranche.0, "newcomer tranche cannot exceed the tranche");
        r.milestone_system = milestone_system;
        r.newcomer_tranche = newcomer_tranche;
        r.tranches = tranches;
    }

    /// Submit a proposal. The attached deposit must cover its storage; any excess is refunded.
    #[payable]
    pub fn submit(&mut self, round_id: u64, title: String, body: String) -> u64 {
        ensure!(title.len() <= MAX_TITLE, "title too long");
        ensure!(body.len() <= MAX_BODY, "body too long");
        let round = self.rounds.get(round_id as u32).or_fail("no such round");
        ensure!(round.open, "round is closed");
        let slots = vec![None; round.models.len()];
        let models = round.models.len() as u64;
        let author = env::predecessor_account_id();
        let now = env::block_timestamp_ms();
        let before = env::storage_usage();
        let record = self.snapshot(&author, now);
        let mut h = self.history.get(&author).cloned().unwrap_or(History { first_seen_ms: now, ..Default::default() });
        h.submitted += 1;
        self.history.insert(author.clone(), h);
        self.rounds.get_mut(round_id as u32).unwrap().proposal_count += 1;
        self.proposals.push(Proposal {
            round_id,
            author,
            title,
            body,
            seed: Self::seed(),
            submitted_ms: now,
            slots,
            finalized: false,
            pending: false,
            outcome: None,
            record,
            stage: 0,
            evidence: None,
            dao_proposal_ids: vec![],
            completed: false,
            past: vec![],
        });
        self.proposals.flush();
        self.history.flush();
        self.rounds.flush();
        let reserved = SLOT_RESERVE_BYTES * models;
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
                "proposal_id": proposal_id, "stage": p.stage, "slot": slot, "model": model, "score": parsed.score,
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

    /// Settle the current stage once its review window has closed.
    ///
    /// Stage 0 (the proposal): passing files the first tranche on the DAO (the newcomer tranche if the applicant
    /// has never delivered a milestone), or wins the bounty in a honeypot round. Stage n (milestone n's
    /// evidence): passing counts a delivered milestone and files the next tranche, if any are left.
    pub fn finalize(&mut self, proposal_id: u64) -> PromiseOrValue<Outcome> {
        let p = self.proposals.get(proposal_id as u32).or_fail("no such proposal").clone();
        ensure!(!p.finalized, "already finalized");
        ensure!(!p.pending, "DAO filing in progress");
        let round = self.rounds.get(p.round_id as u32).or_fail("no such round").clone();
        ensure!(env::block_timestamp_ms() > p.submitted_ms + round.window_ms, "review window still open");
        let (median, filled) = finalize::median(&p.slots).unwrap_or((0, 0));
        ensure!(filled >= round.models.len().min(2), "needs at least 2 reviews");
        let passed = median >= round.threshold && !finalize::flagged_injection(&p.slots);
        let mut outcome = Outcome { median, passed, dao_proposal_id: None, paid: None, amount: U128(0) };
        if passed {
            let mut h = self.history.get(&p.author).cloned().unwrap_or_default();
            if p.stage == 0 { h.passed += 1 } else { h.delivered += 1 }
            self.history.insert(p.author.clone(), h);
        }
        let more_tranches = (p.dao_proposal_ids.len() as u8) < round.tranches;
        match (passed, &round.kind) {
            (true, RoundKind::Honeypot) if round.bounty.0 > 0 => {
                outcome.paid = Some(round.bounty);
                let r = self.rounds.get_mut(p.round_id as u32).unwrap();
                r.bounty = U128(0);
                r.open = false;
                let _ = Promise::new(p.author.clone()).transfer(NearToken::from_yoctonear(round.bounty.0));
            }
            (true, RoundKind::Grant) if more_tranches => {
                ensure!(round.bonds.0 >= round.dao_bond.0, "round has no bonds left for DAO proposals");
                let amount = if p.stage == 0 && p.record.delivered == 0 { round.newcomer_tranche } else { round.tranche };
                outcome.amount = amount;
                self.rounds.get_mut(p.round_id as u32).unwrap().bonds = U128(round.bonds.0 - round.dao_bond.0);
                let prop = self.proposals.get_mut(proposal_id as u32).unwrap();
                prop.pending = true;
                prop.outcome = Some(outcome);
                let args = near_sdk::serde_json::json!({"proposal": {
                    "description": format!("Sieve round {} proposal {} tranche {}: {}", p.round_id, proposal_id,
                        p.dao_proposal_ids.len() + 1, p.title),
                    "kind": {"Transfer": {"token_id": "", "receiver_id": p.author, "amount": amount}},
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
        prop.completed = passed && !more_tranches;
        prop.outcome = Some(outcome.clone());
        PromiseOrValue::Value(outcome)
    }

    /// Result of the DAO's add_proposal. On failure the bond (refunded by the runtime) goes back to the round,
    /// and finalize can be retried.
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
                p.dao_proposal_ids.push(id);
                outcome.dao_proposal_id = Some(id);
                p.outcome = Some(outcome.clone());
            }
            None => {
                p.outcome = None;
                let author = p.author.clone();
                let stage = p.stage;
                let r = self.rounds.get_mut(round_id as u32).unwrap();
                if r.open {
                    r.bonds = U128(r.bonds.0 + r.dao_bond.0);
                } else if r.dao_bond.0 > 0 {
                    let _ = Promise::new(r.creator.clone()).transfer(NearToken::from_yoctonear(r.dao_bond.0));
                }
                // finalize will count the pass again on retry
                if let Some(h) = self.history.get_mut(&author) {
                    if stage == 0 { h.passed = h.passed.saturating_sub(1) } else { h.delivered = h.delivered.saturating_sub(1) }
                }
            }
        }
        outcome
    }

    /// Ask for the next milestone review: the author submits delivery evidence for the tranche last paid.
    /// The contract first checks with the DAO that this tranche's payout proposal was approved by members.
    /// The deposit covers storage for the evidence and the review slots; the rest is refunded.
    #[payable]
    pub fn submit_milestone(&mut self, proposal_id: u64, evidence: String) -> Promise {
        ensure!(evidence.len() <= MAX_EVIDENCE, "evidence too long");
        let p = self.proposals.get(proposal_id as u32).or_fail("no such proposal").clone();
        ensure!(env::predecessor_account_id() == p.author, "only the author can submit milestones");
        let passed = p.finalized && p.outcome.as_ref().is_some_and(|o| o.passed);
        ensure!(passed, "current stage has not passed");
        let round = self.rounds.get(p.round_id as u32).or_fail("no such round");
        ensure!(!p.completed && !round.milestone_system.is_empty(), "no milestones left for this proposal");
        let paid = *p.dao_proposal_ids.get(p.stage as usize).or_fail("no payout filed for this stage");
        let need = env::storage_byte_cost().saturating_mul(
            (evidence.len() as u64 + 100 + SLOT_RESERVE_BYTES * round.models.len() as u64) as u128);
        let attached = env::attached_deposit();
        ensure!(attached >= need, format!("storage deposit of {} yoctoNEAR required", need.as_yoctonear()));
        Promise::new(round.dao.clone())
            .function_call("get_proposal".to_string(), near_sdk::serde_json::json!({"id": paid}).to_string().into_bytes(),
                NearToken::from_yoctonear(0), Gas::from_tgas(10))
            .then(Promise::new(env::current_account_id()).function_call(
                "on_milestone_check".to_string(),
                near_sdk::serde_json::json!({"proposal_id": proposal_id, "evidence": evidence, "deposit": U128(attached.as_yoctonear())})
                    .to_string().into_bytes(),
                NearToken::from_yoctonear(0), Gas::from_tgas(20)))
    }

    /// Opens the milestone review if the DAO approved the last payout; otherwise refunds the deposit.
    #[private]
    pub fn on_milestone_check(&mut self, proposal_id: u64, evidence: String, deposit: U128) -> bool {
        let approved = env::promise_result_checked(0, 100_000)
            .ok()
            .and_then(|v| near_sdk::serde_json::from_slice::<near_sdk::serde_json::Value>(&v).ok())
            .is_some_and(|v| v["status"] == "Approved");
        let p = self.proposals.get(proposal_id as u32).or_fail("no such proposal").clone();
        if !approved {
            env::log_str("milestone not opened: the DAO has not approved the last payout");
            let _ = Promise::new(p.author).transfer(NearToken::from_yoctonear(deposit.0));
            return false;
        }
        let now = env::block_timestamp_ms();
        let record = self.snapshot(&p.author, now);
        let models = self.rounds.get(p.round_id as u32).unwrap().models.len();
        let before = env::storage_usage();
        let prop = self.proposals.get_mut(proposal_id as u32).unwrap();
        prop.past.push(PastStage { seed: prop.seed, record: prop.record.clone(), evidence: prop.evidence.clone() });
        prop.stage += 1;
        prop.evidence = Some(evidence);
        prop.slots = vec![None; models];
        prop.submitted_ms = now;
        prop.seed = Self::seed();
        prop.finalized = false;
        prop.outcome = None;
        prop.record = record;
        self.proposals.flush();
        let used = env::storage_usage().saturating_sub(before) + SLOT_RESERVE_BYTES * models as u64;
        let cost = env::storage_byte_cost().saturating_mul(used as u128).as_yoctonear();
        if deposit.0 > cost {
            let _ = Promise::new(p.author).transfer(NearToken::from_yoctonear(deposit.0 - cost));
        }
        true
    }

    pub fn get_record(&self, account_id: AccountId) -> Record {
        self.snapshot(&account_id, env::block_timestamp_ms())
    }

    /// The exact request bytes a reviewer must send to NEAR AI Cloud for this proposal and slot.
    pub fn review_request(&self, proposal_id: u64, slot: u8) -> Base64VecU8 {
        Base64VecU8(self.request_bytes(proposal_id, slot))
    }

    /// The request for any stage, current or earlier, for re-verifying old reviews.
    pub fn stage_request(&self, proposal_id: u64, stage: u8, slot: u8) -> Base64VecU8 {
        let p = self.proposals.get(proposal_id as u32).or_fail("no such proposal");
        if stage == p.stage {
            return Base64VecU8(self.request_bytes(proposal_id, slot));
        }
        let past = p.past.get(stage as usize).or_fail("no such stage");
        let round = self.rounds.get(p.round_id as u32).or_fail("no such round");
        let model = round.models.get(slot as usize).or_fail("no such slot");
        let system = if stage == 0 { &round.system } else { &round.milestone_system };
        Base64VecU8(request::build(model, system, p.round_id, proposal_id, &p.title, &p.body, past.seed, &past.record,
            stage, past.evidence.as_deref()))
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
        let system = if p.stage == 0 { &round.system } else { &round.milestone_system };
        request::build(model, system, p.round_id, proposal_id, &p.title, &p.body, p.seed, &p.record, p.stage, p.evidence.as_deref())
    }

    fn snapshot(&self, account: &AccountId, now: u64) -> Record {
        self.history.get(account).map_or_else(Record::default, |h| Record {
            days: now.saturating_sub(h.first_seen_ms) / DAY_MS,
            submitted: h.submitted,
            passed: h.passed,
            delivered: h.delivered,
        })
    }

    fn seed() -> u64 {
        let bytes: [u8; 4] = env::random_seed()[..4].try_into().unwrap();
        u32::from_le_bytes(bytes) as u64
    }

    #[cfg(test)]
    pub(crate) fn set_record_for_test(&mut self, account: AccountId, r: Record) {
        let now = env::block_timestamp_ms();
        self.history.insert(account, History { first_seen_ms: now - r.days * DAY_MS, submitted: r.submitted, passed: r.passed, delivered: r.delivered });
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
#[cfg(test)]
mod milestone_tests;
