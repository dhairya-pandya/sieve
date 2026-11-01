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
