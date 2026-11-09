use near_sdk::json_types::{Base64VecU8, U128};
use near_sdk::store::{LookupMap, Vector};
use near_sdk::{env, near, require, AccountId, NearToken, PanicOnDefault, Promise};

mod request;

pub const MAX_TITLE: usize = 200;
pub const MAX_BODY: usize = 8_000;
pub const MAX_MODELS: usize = 5;

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
        require!(env::predecessor_account_id() == self.owner, "only the owner registers signers");
        require!(public_key_hex.len() == 64 && public_key_hex.bytes().all(|b| b.is_ascii_hexdigit()), "key must be 32 bytes hex");
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
        window_ms: u64,
    ) -> u64 {
        require!(!models.is_empty() && models.len() <= MAX_MODELS, "a round needs 1 to 5 models");
        require!(threshold <= 10, "threshold is a score from 0 to 10");
        require!(window_ms > 0, "window must be positive");
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
        require!(title.len() <= MAX_TITLE, "title too long");
        require!(body.len() <= MAX_BODY, "body too long");
        let round = self.rounds.get(round_id as u32).expect("no such round");
        require!(round.open, "round is closed");
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
            outcome: None,
        });
        self.proposals.flush();
        let cost = env::storage_byte_cost().saturating_mul((env::storage_usage() - before) as u128);
        let attached = env::attached_deposit();
        require!(attached >= cost, format!("storage deposit of {} yoctoNEAR required", cost.as_yoctonear()));
        let refund = attached.saturating_sub(cost);
        if refund > NearToken::from_yoctonear(0) {
            let _ = Promise::new(env::predecessor_account_id()).transfer(refund);
        }
        self.proposals.len() as u64 - 1
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
        let p = self.proposals.get(proposal_id as u32).expect("no such proposal");
        let round = self.rounds.get(p.round_id as u32).expect("no such round");
        let model = round.models.get(slot as usize).expect("no such slot");
        request::build(model, &round.system, p.round_id, proposal_id, &p.title, &p.body, p.seed)
    }

    #[cfg(test)]
    pub(crate) fn set_seed_for_test(&mut self, proposal_id: u64, seed: u64) {
        self.proposals.get_mut(proposal_id as u32).unwrap().seed = seed;
    }
}

#[cfg(test)]
mod tests;
