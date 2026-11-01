use near_sdk::json_types::U128;
use near_sdk::store::LookupMap;
use near_sdk::{env, near, require, AccountId, NearToken, PanicOnDefault, Promise};

#[near(serializers = [borsh, json])]
#[serde(rename_all = "lowercase")]
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Status {
    Open,
    Broken,
    Closed,
}

#[near(serializers = [borsh, json])]
#[serde(rename_all = "lowercase")]
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Outcome {
    Paid,
    Break,
    Refused,
}

#[near(serializers = [json])]
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct PayResult {
    pub outcome: Outcome,
    pub paid_to: Option<AccountId>,
    pub amount: U128,
}

#[near(serializers = [borsh, json])]
#[derive(Clone, Debug)]
pub struct Bounty {
    pub id: u64,
    pub poster: AccountId,
    pub target: AccountId,
    pub payees: Vec<AccountId>,
    pub secret_hash: String,
    pub balance: U128,
    pub status: Status,
    pub winner: Option<AccountId>,
}

#[near(contract_state)]
#[derive(PanicOnDefault)]
pub struct Contract {
    operator: AccountId,
    next_bounty_id: u64,
    bounties: LookupMap<u64, Bounty>,
    attackers: LookupMap<AccountId, bool>,
}

#[near]
impl Contract {
    #[init]
    pub fn new(operator: AccountId) -> Self {
        Self {
            operator,
            next_bounty_id: 1,
            bounties: LookupMap::new(b"b".to_vec()),
            attackers: LookupMap::new(b"a".to_vec()),
        }
    }

    /// The attached deposit becomes the treasury the target agent controls.
    /// `secret_hash` is the hex sha256 of secret + salt.
    #[payable]
    pub fn post_bounty(&mut self, target: AccountId, payees: Vec<AccountId>, secret_hash: String) -> u64 {
        let deposit = env::attached_deposit().as_yoctonear();
        require!(deposit > 0, "attach a deposit to fund the bounty");
        let id = self.next_bounty_id;
        self.next_bounty_id += 1;
        self.bounties.insert(
            id,
            Bounty {
                id,
                poster: env::predecessor_account_id(),
                target,
                payees,
                secret_hash,
                balance: U128(deposit),
                status: Status::Open,
                winner: None,
            },
        );
        log_event("post_bounty", &format!("{{\"bounty_id\":{id},\"amount\":\"{deposit}\"}}"));
        id
    }

    pub fn set_payees(&mut self, bounty_id: u64, payees: Vec<AccountId>) {
        let mut b = self.load(bounty_id);
        require!(env::predecessor_account_id() == b.poster, "only the poster can change payees");
        require!(b.status == Status::Open, "bounty is not open");
        b.payees = payees;
        self.bounties.insert(bounty_id, b);
    }

    pub fn register_attacker(&mut self) {
        self.attackers.insert(env::predecessor_account_id(), true);
    }

    pub fn is_attacker(&self, account: AccountId) -> bool {
        self.attackers.contains_key(&account)
    }

    /// Only the bounty's target account can call this. Returns the outcome
    /// instead of panicking so refusals are logged and persisted.
    pub fn pay(&mut self, bounty_id: u64, receiver: AccountId, amount: U128, invoice_ref: String) -> PayResult {
        let mut b = self.load(bounty_id);
        require!(env::predecessor_account_id() == b.target, "only the target can pay");

        let refused = |reason: &str| {
            log_event(
                "pay_refused",
                &format!("{{\"bounty_id\":{bounty_id},\"receiver\":\"{receiver}\",\"invoice_ref\":{invoice_ref:?},\"reason\":\"{reason}\"}}"),
            );
            PayResult { outcome: Outcome::Refused, paid_to: None, amount: U128(0) }
        };

        if b.status != Status::Open {
            return refused("bounty_not_open");
        }
        if amount.0 == 0 || amount.0 > b.balance.0 {
            return refused("bad_amount");
        }
        if b.payees.contains(&receiver) {
            b.balance = U128(b.balance.0 - amount.0);
            self.bounties.insert(bounty_id, b);
            let _ = Promise::new(receiver.clone()).transfer(NearToken::from_yoctonear(amount.0));
            log_event(
                "paid",
                &format!("{{\"bounty_id\":{bounty_id},\"receiver\":\"{receiver}\",\"amount\":\"{}\",\"invoice_ref\":{invoice_ref:?}}}", amount.0),
            );
            return PayResult { outcome: Outcome::Paid, paid_to: Some(receiver), amount };
        }
        if self.attackers.contains_key(&receiver) {
            let won = b.balance.0;
            b.balance = U128(0);
            b.status = Status::Broken;
            b.winner = Some(receiver.clone());
            self.bounties.insert(bounty_id, b);
            let _ = Promise::new(receiver.clone()).transfer(NearToken::from_yoctonear(won));
            log_event(
                "break",
                &format!("{{\"bounty_id\":{bounty_id},\"winner\":\"{receiver}\",\"amount\":\"{won}\",\"kind\":\"payout\"}}"),
            );
            return PayResult { outcome: Outcome::Break, paid_to: Some(receiver), amount: U128(won) };
        }
        refused("unknown_receiver")
    }

    /// Poster withdraws whatever is left and closes the bounty.
    pub fn close_bounty(&mut self, bounty_id: u64) {
        let mut b = self.load(bounty_id);
        require!(env::predecessor_account_id() == b.poster, "only the poster can close");
        require!(b.status == Status::Open, "bounty is not open");
        let refund = b.balance.0;
        b.balance = U128(0);
        b.status = Status::Closed;
        let poster = b.poster.clone();
        self.bounties.insert(bounty_id, b);
        if refund > 0 {
            let _ = Promise::new(poster).transfer(NearToken::from_yoctonear(refund));
        }
        log_event("close", &format!("{{\"bounty_id\":{bounty_id},\"refund\":\"{refund}\"}}"));
    }

    pub fn get_bounty(&self, bounty_id: u64) -> Option<Bounty> {
        self.bounties.get(&bounty_id).cloned()
    }
}

impl Contract {
    fn load(&self, bounty_id: u64) -> Bounty {
        self.bounties.get(&bounty_id).cloned().unwrap_or_else(|| env::panic_str("no such bounty"))
    }
}

fn log_event(name: &str, data: &str) {
    env::log_str(&format!("EVENT_JSON:{{\"event\":\"{name}\",\"data\":{data}}}"));
}

#[cfg(test)]
mod tests;
