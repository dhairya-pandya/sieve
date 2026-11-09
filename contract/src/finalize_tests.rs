use crate::review_tests::*;
use crate::tests::*;
use crate::*;
use near_sdk::test_utils::{accounts, VMContextBuilder};
use near_sdk::{testing_env, PromiseResult, RuntimeFeesConfig};
use std::collections::HashMap;

const AFTER: u64 = 2_000 + 600_001;

fn scores(c: &mut Sieve, s: [Option<&str>; 3]) {
    for (slot, content) in s.iter().enumerate() {
        if let Some(content) = content {
            post(c, 0, slot as u8, slot as u8 + 1, content, 3_000);
        }
    }
}

fn honeypot_round() -> Sieve {
    let mut c = three_model_round();
    ctx(0, 2 * NEAR, 1_800);
    c.create_round(RoundKind::Honeypot, accounts(3), "rubric".into(),
        MODELS.iter().map(|m| m.to_string()).collect(), 7, U128(0), U128(0), 600_000);
    ctx(1, NEAR, 2_000);
    let pid = c.submit(1, "free money".into(), "body".into());
    for slot in 0..3u8 {
        post(&mut c, pid, slot, slot + 1, r#"{"score":9,"flags":[]}"#, 3_000);
    }
    c
}

#[test]
#[should_panic(expected = "review window still open")]
fn finalize_rejects_early() {
    let mut c = three_model_round();
    scores(&mut c, [Some(r#"{"score":8}"#), Some(r#"{"score":8}"#), None]);
    ctx(2, 0, 3_000);
    let _ = c.finalize(0);
}

#[test]
#[should_panic(expected = "needs at least 2 reviews")]
fn finalize_needs_two_slots() {
    let mut c = three_model_round();
    scores(&mut c, [Some(r#"{"score":8}"#), None, None]);
    ctx(2, 0, AFTER);
    let _ = c.finalize(0);
}

#[test]
fn median_of_three_files_dao_proposal() {
    let mut c = three_model_round();
    scores(&mut c, [Some(r#"{"score":2}"#), Some(r#"{"score":9}"#), Some(r#"{"score":8}"#)]);
    ctx(2, 0, AFTER);
    let _ = c.finalize(0);
    let p = c.get_proposal(0).unwrap();
    assert!(p.pending && !p.finalized);
    assert_eq!(p.outcome.unwrap().median, 8);
    assert_eq!(c.get_round(0).unwrap().bonds, U128(NEAR - NEAR / 10));
}

#[test]
fn failing_score_finalizes_without_dao_call() {
    let mut c = three_model_round();
    scores(&mut c, [Some(r#"{"score":2}"#), Some(r#"{"score":6}"#), Some(r#"{"score":9}"#)]);
    ctx(2, 0, AFTER);
    let _ = c.finalize(0);
    let p = c.get_proposal(0).unwrap();
    assert!(p.finalized && !p.pending);
    assert_eq!(p.outcome.unwrap(), Outcome { median: 6, passed: false, dao_proposal_id: None, paid: None });
}

#[test]
fn injection_flag_blocks_pass() {
    let mut c = three_model_round();
    scores(&mut c, [Some(r#"{"score":9}"#), Some(r#"{"score":9,"flags":["injection"]}"#), Some(r#"{"score":9}"#)]);
    ctx(2, 0, AFTER);
    let _ = c.finalize(0);
    assert!(!c.get_proposal(0).unwrap().outcome.unwrap().passed);
}

#[test]
fn honeypot_pays_once() {
    let mut c = honeypot_round();
    ctx(2, 0, AFTER);
    let _ = c.finalize(1);
    let p = c.get_proposal(1).unwrap();
    assert!(p.finalized);
    assert_eq!(p.outcome.unwrap().paid, Some(U128(2 * NEAR)));
    let r = c.get_round(1).unwrap();
    assert_eq!((r.bounty, r.open), (U128(0), false));
}

#[test]
#[should_panic(expected = "already finalized")]
fn finalize_twice_fails() {
    let mut c = honeypot_round();
    ctx(2, 0, AFTER);
    let _ = c.finalize(1);
    let _ = c.finalize(1);
}

fn callback(c: &mut Sieve, result: PromiseResult) -> Outcome {
    let mut b = VMContextBuilder::new();
    b.current_account_id(accounts(4)).predecessor_account_id(accounts(4)).block_timestamp(AFTER * 1_000_000);
    testing_env!(b.build(), near_sdk::test_vm_config(), RuntimeFeesConfig::test(), HashMap::default(), vec![result]);
    let r = c.on_dao_proposal(0);
    r
}

#[test]
fn dao_callback_success_records_id() {
    let mut c = three_model_round();
    scores(&mut c, [Some(r#"{"score":8}"#), Some(r#"{"score":9}"#), Some(r#"{"score":8}"#)]);
    ctx(2, 0, AFTER);
    let _ = c.finalize(0);
    let out = callback(&mut c, PromiseResult::Successful(b"17".to_vec()));
    assert_eq!(out.dao_proposal_id, Some(17));
    let p = c.get_proposal(0).unwrap();
    assert!(p.finalized && !p.pending);
}

#[test]
fn dao_callback_failure_is_retryable() {
    let mut c = three_model_round();
    scores(&mut c, [Some(r#"{"score":8}"#), Some(r#"{"score":9}"#), Some(r#"{"score":8}"#)]);
    ctx(2, 0, AFTER);
    let _ = c.finalize(0);
    callback(&mut c, PromiseResult::Failed);
    let p = c.get_proposal(0).unwrap();
    assert!(!p.finalized && !p.pending);
    assert_eq!(c.get_round(0).unwrap().bonds, U128(NEAR));
    ctx(2, 0, AFTER + 1);
    let _ = c.finalize(0);
    assert!(c.get_proposal(0).unwrap().pending);
}
