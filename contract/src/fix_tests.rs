use crate::review_tests::*;
use crate::tests::*;
use crate::*;
use near_sdk::test_utils::accounts;

#[test]
#[should_panic(expected = "models must be distinct")]
fn create_round_rejects_duplicate_models() {
    ctx(0, 0, 1_000);
    let mut c = Sieve::new(accounts(0));
    ctx(0, NEAR, 1_000);
    c.create_round(RoundKind::Grant, accounts(3), "s".into(), vec!["a".into(), "a".into(), "b".into()], 7, U128(1), U128(1), 600_000);
}

#[test]
fn stored_flags_are_known_and_capped() {
    let mut c = three_model_round();
    let many: Vec<String> = (0..50).map(|i| format!("\"flag{i}{}\"", "x".repeat(100))).collect();
    let content = format!(r#"{{"score":3,"flags":["low_effort",{},"injection","low_effort"]}}"#, many.join(","));
    post(&mut c, 0, 0, 1, &content, 3_000);
    assert_eq!(c.get_proposal(0).unwrap().slots[0].clone().unwrap().flags, vec!["low_effort".to_string(), "injection".to_string()]);
}

#[test]
#[should_panic(expected = "storage deposit")]
fn submit_reserves_storage_for_reviews() {
    let mut c = three_model_round();
    // Enough for the proposal itself but not for three review slots.
    ctx(1, 10u128.pow(19) * 400, 2_000);
    c.submit(0, "t".into(), "b".into());
}

#[test]
fn fund_round_adds_bonds() {
    let mut c = three_model_round();
    ctx(2, NEAR, 2_000);
    c.fund_round(0);
    assert_eq!(c.get_round(0).unwrap().bonds, U128(2 * NEAR));
}

#[test]
fn creator_closes_round_and_gets_funds_back() {
    let mut c = three_model_round();
    ctx(0, 0, 2_000);
    let refunded = c.close_round(0);
    assert_eq!(refunded, U128(NEAR));
    let r = c.get_round(0).unwrap();
    assert!(!r.open && r.bonds == U128(0));
}

#[test]
#[should_panic(expected = "only the round creator")]
fn only_creator_closes_round() {
    let mut c = three_model_round();
    ctx(1, 0, 2_000);
    c.close_round(0);
}
