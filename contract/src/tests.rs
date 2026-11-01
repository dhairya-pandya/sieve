use super::*;
use near_sdk::test_utils::VMContextBuilder;
use near_sdk::testing_env;

fn acc(s: &str) -> AccountId {
    s.parse().unwrap()
}

fn ctx(predecessor: &str, deposit: NearToken) -> VMContextBuilder {
    let mut b = VMContextBuilder::new();
    b.predecessor_account_id(acc(predecessor))
        .signer_account_id(acc(predecessor))
        .attached_deposit(deposit);
    b
}

const TEN: NearToken = NearToken::from_near(10);
const ONE: u128 = 10u128.pow(24);

/// Bounty 1: poster "poster", target "target", payee "vendor", 10 NEAR treasury,
/// "atk" registered as an attacker.
fn setup() -> (Contract, u64) {
    testing_env!(ctx("deployer", NearToken::from_yoctonear(0)).build());
    let mut c = Contract::new(acc("op"));
    testing_env!(ctx("poster", TEN).build());
    let id = c.post_bounty(acc("target"), vec![acc("vendor")], "hash".to_string());
    testing_env!(ctx("atk", NearToken::from_yoctonear(0)).build());
    c.register_attacker();
    (c, id)
}

fn as_account(name: &str) {
    testing_env!(ctx(name, NearToken::from_yoctonear(0)).build());
}

#[test]
fn pay_to_approved_payee_is_paid_not_break() {
    let (mut c, id) = setup();
    as_account("target");
    let r = c.pay(id, acc("vendor"), U128(ONE), "inv-1".into());
    assert_eq!(r.outcome, Outcome::Paid);
    assert_eq!(r.paid_to, Some(acc("vendor")));
    let b = c.get_bounty(id).unwrap();
    assert_eq!(b.balance.0, 9 * ONE);
    assert_eq!(b.status, Status::Open);
}

#[test]
fn pay_to_registered_attacker_off_list_is_break() {
    let (mut c, id) = setup();
    as_account("target");
    let r = c.pay(id, acc("atk"), U128(ONE), "inv-2".into());
    assert_eq!(r.outcome, Outcome::Break);
    assert_eq!(r.paid_to, Some(acc("atk")));
    assert_eq!(r.amount.0, 10 * ONE);
    let b = c.get_bounty(id).unwrap();
    assert_eq!(b.balance.0, 0);
    assert_eq!(b.status, Status::Broken);
    assert_eq!(b.winner, Some(acc("atk")));
}

#[test]
fn account_both_payee_and_attacker_is_normal_payment() {
    let (mut c, id) = setup();
    testing_env!(ctx("poster", NearToken::from_yoctonear(0)).build());
    c.set_payees(id, vec![acc("vendor"), acc("atk")]);
    as_account("target");
    let r = c.pay(id, acc("atk"), U128(ONE), "inv-3".into());
    assert_eq!(r.outcome, Outcome::Paid);
    assert_eq!(c.get_bounty(id).unwrap().status, Status::Open);
}

#[test]
fn pay_to_unknown_account_refused() {
    let (mut c, id) = setup();
    as_account("target");
    let r = c.pay(id, acc("stranger"), U128(ONE), "inv-4".into());
    assert_eq!(r.outcome, Outcome::Refused);
    assert_eq!(c.get_bounty(id).unwrap().balance.0, 10 * ONE);
}

#[test]
fn pay_zero_or_over_balance_refused() {
    let (mut c, id) = setup();
    as_account("target");
    let zero = c.pay(id, acc("vendor"), U128(0), "inv-5".into());
    let over = c.pay(id, acc("vendor"), U128(11 * ONE), "inv-6".into());
    assert_eq!(zero.outcome, Outcome::Refused);
    assert_eq!(over.outcome, Outcome::Refused);
    let b = c.get_bounty(id).unwrap();
    assert_eq!(b.balance.0, 10 * ONE);
    assert_eq!(b.status, Status::Open);
}

#[test]
#[should_panic(expected = "only the target")]
fn only_target_can_call_pay() {
    let (mut c, id) = setup();
    as_account("atk");
    c.pay(id, acc("atk"), U128(ONE), "inv-7".into());
}

#[test]
#[should_panic(expected = "only the poster")]
fn only_poster_can_set_payees() {
    let (mut c, id) = setup();
    as_account("atk");
    c.set_payees(id, vec![acc("atk")]);
}

#[test]
#[should_panic(expected = "only the poster")]
fn only_poster_can_close() {
    let (mut c, id) = setup();
    as_account("atk");
    c.close_bounty(id);
}

#[test]
fn second_pay_after_break_refused() {
    let (mut c, id) = setup();
    as_account("target");
    c.pay(id, acc("atk"), U128(ONE), "inv-8".into());
    let r = c.pay(id, acc("vendor"), U128(ONE), "inv-9".into());
    assert_eq!(r.outcome, Outcome::Refused);
}

#[test]
fn close_refunds_remaining_and_blocks_further_pay() {
    let (mut c, id) = setup();
    testing_env!(ctx("poster", NearToken::from_yoctonear(0)).build());
    c.close_bounty(id);
    let b = c.get_bounty(id).unwrap();
    assert_eq!(b.status, Status::Closed);
    assert_eq!(b.balance.0, 0);
    as_account("target");
    let r = c.pay(id, acc("vendor"), U128(ONE), "inv-10".into());
    assert_eq!(r.outcome, Outcome::Refused);
}

// ---- Task 3: secret break, credit, fees, leads ----

fn secret_hash() -> String {
    sha256_hex("s3cretsalt")
}

fn setup_with_secret() -> (Contract, u64) {
    testing_env!(ctx("deployer", NearToken::from_yoctonear(0)).build());
    let mut c = Contract::new(acc("op"));
    testing_env!(ctx("poster", TEN).build());
    let id = c.post_bounty(acc("target"), vec![acc("vendor")], secret_hash());
    testing_env!(ctx("atk", NearToken::from_yoctonear(0)).build());
    c.register_attacker();
    testing_env!(ctx("atk2", NearToken::from_yoctonear(0)).build());
    c.register_attacker();
    (c, id)
}

#[test]
fn claim_secret_right_pays_and_closes() {
    let (mut c, id) = setup_with_secret();
    as_account("atk");
    assert!(c.claim_secret(id, "s3cret".into(), "salt".into()));
    let b = c.get_bounty(id).unwrap();
    assert_eq!(b.status, Status::Broken);
    assert_eq!(b.winner, Some(acc("atk")));
    assert_eq!(b.balance.0, 0);
}

#[test]
fn claim_secret_wrong_returns_false_and_keeps_open() {
    let (mut c, id) = setup_with_secret();
    as_account("atk");
    assert!(!c.claim_secret(id, "guess".into(), "salt".into()));
    let b = c.get_bounty(id).unwrap();
    assert_eq!(b.status, Status::Open);
    assert_eq!(b.balance.0, 10 * ONE);
}

#[test]
fn claim_secret_after_break_returns_false() {
    let (mut c, id) = setup_with_secret();
    as_account("atk");
    assert!(c.claim_secret(id, "s3cret".into(), "salt".into()));
    as_account("atk2");
    assert!(!c.claim_secret(id, "s3cret".into(), "salt".into()));
    assert_eq!(c.get_bounty(id).unwrap().winner, Some(acc("atk")));
}

fn fund_credit(c: &mut Contract, who: &str, amount: u128) {
    testing_env!(ctx(who, NearToken::from_yoctonear(amount)).build());
    c.deposit_credit();
}

#[test]
#[should_panic(expected = "only the operator")]
fn record_fees_only_operator() {
    let (mut c, id) = setup_with_secret();
    fund_credit(&mut c, "atk", ONE);
    as_account("atk");
    c.record_fees(id, vec![(acc("atk"), U128(1))]);
}

#[test]
fn record_fees_debits_credit_and_credits_poster() {
    let (mut c, id) = setup_with_secret();
    fund_credit(&mut c, "atk", ONE);
    fund_credit(&mut c, "atk2", ONE);
    as_account("op");
    c.record_fees(id, vec![(acc("atk"), U128(300)), (acc("atk2"), U128(200))]);
    assert_eq!(c.get_credit(acc("atk")).0, ONE - 300);
    assert_eq!(c.get_credit(acc("atk2")).0, ONE - 200);
    assert_eq!(c.get_fees(acc("poster")).0, 500);
    as_account("poster");
    assert_eq!(c.withdraw_fees().0, 500);
    assert_eq!(c.get_fees(acc("poster")).0, 0);
}

#[test]
#[should_panic(expected = "insufficient credit")]
fn record_fees_panics_when_credit_short() {
    let (mut c, id) = setup_with_secret();
    fund_credit(&mut c, "atk", 100);
    as_account("op");
    c.record_fees(id, vec![(acc("atk"), U128(101))]);
}

fn post_lead_as_atk(c: &mut Contract, id: u64) -> u64 {
    as_account("atk");
    c.post_lead(id, "trusts emails quoting an invoice".into(), U128(ONE), "lead-hash".into())
}

#[test]
#[should_panic(expected = "exact price")]
fn unlock_lead_requires_exact_price() {
    let (mut c, id) = setup_with_secret();
    let lead = post_lead_as_atk(&mut c, id);
    testing_env!(ctx("atk2", NearToken::from_yoctonear(ONE - 1)).build());
    c.unlock_lead(lead);
}

#[test]
fn unlock_lead_marks_buyer_and_pays_author() {
    let (mut c, id) = setup_with_secret();
    let lead = post_lead_as_atk(&mut c, id);
    assert!(!c.is_unlocked(lead, acc("atk2")));
    testing_env!(ctx("atk2", NearToken::from_yoctonear(ONE)).build());
    c.unlock_lead(lead);
    assert!(c.is_unlocked(lead, acc("atk2")));
    assert_eq!(c.get_lead(lead).unwrap().author, acc("atk"));
}

#[test]
fn author_is_unlocked_by_default() {
    let (mut c, id) = setup_with_secret();
    let lead = post_lead_as_atk(&mut c, id);
    assert!(c.is_unlocked(lead, acc("atk")));
}
