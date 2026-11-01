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

#[near(serializers = [borsh, json])]
#[derive(Clone, Debug)]
pub struct Lead {
    pub id: u64,
    pub bounty_id: u64,
    pub author: AccountId,
    pub title: String,
    pub price: U128,
    pub content_hash: String,
}

#[near(contract_state)]
#[derive(PanicOnDefault)]
pub struct Contract {
    operator: AccountId,
    next_bounty_id: u64,
    bounties: LookupMap<u64, Bounty>,
    attackers: LookupMap<AccountId, bool>,
    credits: LookupMap<AccountId, u128>,
    fees: LookupMap<AccountId, u128>,
    next_lead_id: u64,
    leads: LookupMap<u64, Lead>,
    unlocked: LookupMap<String, bool>,
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
            credits: LookupMap::new(b"c".to_vec()),
            fees: LookupMap::new(b"f".to_vec()),
            next_lead_id: 1,
            leads: LookupMap::new(b"l".to_vec()),
            unlocked: LookupMap::new(b"u".to_vec()),
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

    pub fn claim_secret(&mut self, bounty_id: u64, secret: String, salt: String) -> bool {
        let caller = env::predecessor_account_id();
        require!(self.attackers.contains_key(&caller), "register as an attacker first");
        let mut b = self.load(bounty_id);
        if b.status != Status::Open {
            return false;
        }
        if sha256_hex(&format!("{secret}{salt}")) != b.secret_hash {
            return false;
        }
        let won = b.balance.0;
        b.balance = U128(0);
        b.status = Status::Broken;
        b.winner = Some(caller.clone());
        self.bounties.insert(bounty_id, b);
        if won > 0 {
            let _ = Promise::new(caller.clone()).transfer(NearToken::from_yoctonear(won));
        }
        log_event(
            "break",
            &format!("{{\"bounty_id\":{bounty_id},\"winner\":\"{caller}\",\"amount\":\"{won}\",\"kind\":\"secret\"}}"),
        );
        true
    }

    #[payable]
    pub fn deposit_credit(&mut self) {
        let who = env::predecessor_account_id();
        let deposit = env::attached_deposit().as_yoctonear();
        require!(deposit > 0, "attach a deposit");
        let now = self.credits.get(&who).copied().unwrap_or(0);
        self.credits.insert(who, now + deposit);
    }

    pub fn get_credit(&self, account: AccountId) -> U128 {
        U128(self.credits.get(&account).copied().unwrap_or(0))
    }

    pub fn record_fees(&mut self, bounty_id: u64, charges: Vec<(AccountId, U128)>) {
        require!(env::predecessor_account_id() == self.operator, "only the operator can record fees");
        let poster = self.load(bounty_id).poster;
        let mut total = 0u128;
        for (account, fee) in charges {
            let credit = self.credits.get(&account).copied().unwrap_or(0);
            require!(credit >= fee.0, "insufficient credit");
            self.credits.insert(account, credit - fee.0);
            total += fee.0;
        }
        let owed = self.fees.get(&poster).copied().unwrap_or(0);
        self.fees.insert(poster, owed + total);
        log_event("fees", &format!("{{\"bounty_id\":{bounty_id},\"total\":\"{total}\"}}"));
    }

    pub fn withdraw_fees(&mut self) -> U128 {
        let who = env::predecessor_account_id();
        let owed = self.fees.get(&who).copied().unwrap_or(0);
        self.fees.insert(who.clone(), 0);
        if owed > 0 {
            let _ = Promise::new(who).transfer(NearToken::from_yoctonear(owed));
        }
        U128(owed)
    }

    pub fn get_fees(&self, poster: AccountId) -> U128 {
        U128(self.fees.get(&poster).copied().unwrap_or(0))
    }

    pub fn post_lead(&mut self, bounty_id: u64, title: String, price: U128, content_hash: String) -> u64 {
        let author = env::predecessor_account_id();
        require!(self.attackers.contains_key(&author), "register as an attacker first");
        require!(self.bounties.contains_key(&bounty_id), "no such bounty");
        let id = self.next_lead_id;
        self.next_lead_id += 1;
        self.leads.insert(id, Lead { id, bounty_id, author: author.clone(), title, price, content_hash });
        log_event("lead_posted", &format!("{{\"lead_id\":{id},\"bounty_id\":{bounty_id},\"author\":\"{author}\",\"price\":\"{}\"}}", price.0));
        id
    }

    #[payable]
    pub fn unlock_lead(&mut self, lead_id: u64) {
        let lead = self.leads.get(&lead_id).cloned().unwrap_or_else(|| env::panic_str("no such lead"));
        let buyer = env::predecessor_account_id();
        require!(env::attached_deposit().as_yoctonear() == lead.price.0, "attach the exact price");
        require!(!self.is_unlocked(lead_id, buyer.clone()), "already unlocked");
        self.unlocked.insert(format!("{lead_id}:{buyer}"), true);
        let _ = Promise::new(lead.author.clone()).transfer(NearToken::from_yoctonear(lead.price.0));
        log_event("lead_unlocked", &format!("{{\"lead_id\":{lead_id},\"buyer\":\"{buyer}\",\"author\":\"{}\"}}", lead.author));
    }

    pub fn get_lead(&self, lead_id: u64) -> Option<Lead> {
        self.leads.get(&lead_id).cloned()
    }

    pub fn is_unlocked(&self, lead_id: u64, account: AccountId) -> bool {
        match self.leads.get(&lead_id) {
            Some(lead) => lead.author == account || self.unlocked.contains_key(&format!("{lead_id}:{account}")),
            None => false,
        }
    }
}

impl Contract {
    fn load(&self, bounty_id: u64) -> Bounty {
        self.bounties.get(&bounty_id).cloned().unwrap_or_else(|| env::panic_str("no such bounty"))
    }
}

pub(crate) fn sha256_hex(input: &str) -> String {
    env::sha256(input.as_bytes()).iter().map(|b| format!("{b:02x}")).collect()
}

fn log_event(name: &str, data: &str) {
    env::log_str(&format!("EVENT_JSON:{{\"event\":\"{name}\",\"data\":{data}}}"));
}

#[cfg(test)]
mod tests;
