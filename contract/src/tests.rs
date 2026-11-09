use crate::*;
use near_sdk::base64::Engine;
use near_sdk::serde_json::Value;
use near_sdk::test_utils::{accounts, VMContextBuilder};
use near_sdk::testing_env;

pub(crate) const FIXTURE: &str = include_str!("../../tests/fixtures/signed_review.json");
pub(crate) const NEAR: u128 = 10u128.pow(24);

pub(crate) fn fixture() -> Value {
    near_sdk::serde_json::from_str(FIXTURE).unwrap()
}

pub(crate) fn b64(s: &str) -> Vec<u8> {
    near_sdk::base64::engine::general_purpose::STANDARD.decode(s).unwrap()
}

pub(crate) fn ctx(predecessor: usize, deposit: u128, now_ms: u64) {
    let mut b = VMContextBuilder::new();
    b.predecessor_account_id(accounts(predecessor))
        .attached_deposit(NearToken::from_yoctonear(deposit))
        .block_timestamp(now_ms * 1_000_000);
    testing_env!(b.build());
}

/// Contract owned by accounts(0) with one grant round using the fixture's model and system prompt.
pub(crate) fn setup_round(models: Vec<String>, system: &str) -> Sieve {
    ctx(0, 0, 1_000);
    let mut c = Sieve::new(accounts(0));
    ctx(0, NEAR, 1_000);
    c.create_round(RoundKind::Grant, accounts(3), system.to_string(), models, 7, U128(NEAR), U128(NEAR / 10), 600_000);
    c
}

#[test]
fn request_matches_python_fixture() {
    let f = fixture();
    let model = f["model"].as_str().unwrap().to_string();
    let mut c = setup_round(vec![model], f["system"].as_str().unwrap());
    ctx(1, NEAR / 10, 2_000);
    let pid = c.submit(0, f["title"].as_str().unwrap().into(), f["body"].as_str().unwrap().into());
    assert_eq!(pid, 0);
    c.set_seed_for_test(pid, f["seed"].as_u64().unwrap());
    let built: Vec<u8> = c.review_request(pid, 0).into();
    assert_eq!(String::from_utf8(built).unwrap(), String::from_utf8(b64(f["request_b64"].as_str().unwrap())).unwrap());
}

#[test]
fn request_escapes_like_python() {
    // Same strings as tests/test_request.py::test_build_request_escaping.
    let mut c = setup_round(vec!["Qwen/Qwen3.8-27B".into()], "Rubric here");
    ctx(1, NEAR / 10, 2_000);
    let pid = c.submit(0, "Fix \"fees\" \\ path".into(), "Line one\n\tTabbed \u{1} control 🚀 अनुदान".into());
    c.set_seed_for_test(pid, 42);
    let built = String::from_utf8(c.review_request(pid, 0).into()).unwrap();
    assert!(built.contains("\\u0001"));
    assert!(built.contains("🚀") && built.contains("अनुदान"));
    assert!(built.contains("Fix \\\"fees\\\" \\\\ path"));
}

#[test]
#[should_panic(expected = "body too long")]
fn submit_rejects_oversize() {
    let mut c = setup_round(vec!["m".into()], "s");
    ctx(1, NEAR, 2_000);
    c.submit(0, "t".into(), "x".repeat(8_001));
}

#[test]
#[should_panic(expected = "title too long")]
fn submit_rejects_long_title() {
    let mut c = setup_round(vec!["m".into()], "s");
    ctx(1, NEAR, 2_000);
    c.submit(0, "t".repeat(201), "b".into());
}

#[test]
#[should_panic(expected = "storage deposit")]
fn submit_requires_storage_deposit() {
    let mut c = setup_round(vec!["m".into()], "s");
    ctx(1, 0, 2_000);
    c.submit(0, "t".into(), "b".repeat(2_000));
}

#[test]
#[should_panic(expected = "only the owner")]
fn only_owner_registers_signers() {
    let mut c = setup_round(vec!["m".into()], "s");
    ctx(1, 0, 2_000);
    c.register_signer("00".repeat(32), "m".into(), 10_000);
}

#[test]
fn owner_registers_signer() {
    let mut c = setup_round(vec!["m".into()], "s");
    ctx(0, 0, 2_000);
    c.register_signer("ab".repeat(32), "m".into(), 10_000);
    assert_eq!(c.get_signer("ab".repeat(32)).unwrap().model, "m");
}

#[test]
fn seeds_differ_between_proposals() {
    let mut c = setup_round(vec!["m".into()], "s");
    let mut b = VMContextBuilder::new();
    b.predecessor_account_id(accounts(1)).attached_deposit(NearToken::from_yoctonear(NEAR)).random_seed([7; 32]);
    testing_env!(b.build());
    let a = c.submit(0, "t".into(), "b".into());
    b.random_seed([9; 32]);
    testing_env!(b.build());
    let d = c.submit(0, "t".into(), "b".into());
    assert_ne!(c.get_proposal(a).unwrap().seed, c.get_proposal(d).unwrap().seed);
}
