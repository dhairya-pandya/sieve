use crate::review_tests::*;
use crate::tests::*;
use crate::*;
use near_sdk::test_utils::{accounts, VMContextBuilder};
use near_sdk::{testing_env, PromiseResult, RuntimeFeesConfig};
use std::collections::HashMap;

const VECTORS: &str = include_str!("../../tests/fixtures/request_vectors.json");
const AFTER: u64 = 2_000 + 600_001;
const DAY: u64 = 86_400_000;

#[test]
fn request_vectors_match_python() {
    let vs: Vec<near_sdk::serde_json::Value> = near_sdk::serde_json::from_str(VECTORS).unwrap();
    for v in vs {
        let rec: Vec<u64> = v["record"].as_array().unwrap().iter().map(|x| x.as_u64().unwrap()).collect();
        let built = request::build(
            v["model"].as_str().unwrap(), v["system"].as_str().unwrap(), v["round_id"].as_u64().unwrap(),
            v["proposal_id"].as_u64().unwrap(), v["title"].as_str().unwrap(), v["body"].as_str().unwrap(),
            v["seed"].as_u64().unwrap(), &Record { days: rec[0], submitted: rec[1] as u32, passed: rec[2] as u32, delivered: rec[3] as u32 },
            v["stage"].as_u64().unwrap() as u8, v["evidence"].as_str());
        assert_eq!(String::from_utf8(built).unwrap(), v["request"].as_str().unwrap(), "{}", v["name"]);
    }
}

#[test]
fn record_snapshot_counts_earlier_proposals() {
    let mut c = three_model_round();
    ctx(1, NEAR, 2_000 + 3 * DAY);
    let second = c.submit(0, "again".into(), "body".into());
    let r = c.get_proposal(second).unwrap().record;
    assert_eq!((r.days, r.submitted, r.passed, r.delivered), (3, 1, 0, 0));
    assert_eq!(c.get_proposal(0).unwrap().record.submitted, 0);
}

fn milestone_round() -> Sieve {
    let mut c = three_model_round_without_proposal();
    ctx(0, 0, 1_600);
    c.set_milestones(0, "check delivery".into(), U128(NEAR / 5), 3);
    ctx(1, NEAR, 2_000);
    c.submit(0, "title".into(), "body".into());
    c
}

fn pass_stage(c: &mut Sieve, now: u64) {
    for slot in 0..3u8 {
        post(c, 0, slot, slot + 1, r#"{"score":8,"flags":[]}"#, now);
    }
}

fn dao_result(c: &mut Sieve, now: u64, result: PromiseResult) -> Outcome {
    let mut b = VMContextBuilder::new();
    b.current_account_id(accounts(4)).predecessor_account_id(accounts(4)).block_timestamp(now * 1_000_000);
    testing_env!(b.build(), near_sdk::test_vm_config(), RuntimeFeesConfig::test(), HashMap::default(), vec![result]);
    c.on_dao_proposal(0)
}

fn approve_check(c: &mut Sieve, now: u64, status: &str, deposit: u128) -> bool {
    let mut b = VMContextBuilder::new();
    b.current_account_id(accounts(4)).predecessor_account_id(accounts(4)).block_timestamp(now * 1_000_000);
    let body = format!(r#"{{"id":17,"status":"{status}"}}"#).into_bytes();
    testing_env!(b.build(), near_sdk::test_vm_config(), RuntimeFeesConfig::test(), HashMap::default(),
        vec![PromiseResult::Successful(body)]);
    c.on_milestone_check(0, "Released v1, commit abc".into(), U128(deposit))
}

#[test]
fn newcomer_gets_newcomer_tranche() {
    let mut c = milestone_round();
    pass_stage(&mut c, 3_000);
    ctx(2, 0, AFTER);
    let _ = c.finalize(0);
    assert_eq!(c.get_proposal(0).unwrap().outcome.unwrap().amount, U128(NEAR / 5));
}

#[test]
fn applicant_with_delivered_milestone_gets_full_tranche() {
    let mut c = milestone_round();
    c.set_record_for_test(accounts(1), Record { days: 0, submitted: 0, passed: 1, delivered: 1 });
    ctx(1, NEAR, 2_000);
    let pid = c.submit(0, "second".into(), "body".into());
    for slot in 0..3u8 {
        post(&mut c, pid, slot, slot + 1, r#"{"score":8,"flags":[]}"#, 3_000);
    }
    ctx(2, 0, AFTER);
    let _ = c.finalize(pid);
    assert_eq!(c.get_proposal(pid).unwrap().outcome.unwrap().amount, U128(NEAR));
}

#[test]
#[should_panic(expected = "only the round creator")]
fn only_creator_sets_milestones() {
    let mut c = three_model_round_without_proposal();
    ctx(1, 0, 1_600);
    c.set_milestones(0, "x".into(), U128(1), 2);
}

#[test]
#[should_panic(expected = "rules cannot change after the first proposal")]
fn milestones_fixed_after_first_proposal() {
    let mut c = milestone_round();
    ctx(0, 0, 2_500);
    c.set_milestones(0, "x".into(), U128(1), 2);
}

#[test]
#[should_panic(expected = "only the author")]
fn only_author_submits_milestone() {
    let mut c = milestone_round();
    pass_stage(&mut c, 3_000);
    ctx(2, 0, AFTER);
    let _ = c.finalize(0);
    dao_result(&mut c, AFTER, PromiseResult::Successful(b"17".to_vec()));
    ctx(2, NEAR, AFTER + 1);
    let _ = c.submit_milestone(0, "evidence".into());
}

#[test]
#[should_panic(expected = "current stage has not passed")]
fn milestone_needs_passed_stage() {
    let mut c = milestone_round();
    ctx(1, NEAR, 3_000);
    let _ = c.submit_milestone(0, "evidence".into());
}

#[test]
fn approved_dao_payout_opens_milestone_review() {
    let mut c = milestone_round();
    pass_stage(&mut c, 3_000);
    ctx(2, 0, AFTER);
    let _ = c.finalize(0);
    dao_result(&mut c, AFTER, PromiseResult::Successful(b"17".to_vec()));
    assert_eq!(c.get_proposal(0).unwrap().dao_proposal_ids, vec![17]);
    ctx(1, NEAR, AFTER + 1);
    let _ = c.submit_milestone(0, "Released v1, commit abc".into());
    assert!(approve_check(&mut c, AFTER + 2, "Approved", NEAR));
    let p = c.get_proposal(0).unwrap();
    assert_eq!((p.stage, p.finalized, p.evidence.as_deref()), (1, false, Some("Released v1, commit abc")));
    assert!(p.slots.iter().all(Option::is_none));
    let req = String::from_utf8(c.review_request(0, 0).into()).unwrap();
    assert!(req.contains("stage 1") && req.contains("check delivery") && req.contains("Released v1, commit abc"));
}

#[test]
fn unapproved_dao_payout_keeps_stage() {
    let mut c = milestone_round();
    pass_stage(&mut c, 3_000);
    ctx(2, 0, AFTER);
    let _ = c.finalize(0);
    dao_result(&mut c, AFTER, PromiseResult::Successful(b"17".to_vec()));
    ctx(1, NEAR, AFTER + 1);
    let _ = c.submit_milestone(0, "e".into());
    assert!(!approve_check(&mut c, AFTER + 2, "InProgress", NEAR));
    assert_eq!(c.get_proposal(0).unwrap().stage, 0);
}

#[test]
fn passed_milestone_counts_delivery_and_files_next_tranche() {
    let mut c = milestone_round();
    pass_stage(&mut c, 3_000);
    ctx(2, 0, AFTER);
    let _ = c.finalize(0);
    dao_result(&mut c, AFTER, PromiseResult::Successful(b"17".to_vec()));
    ctx(1, NEAR, AFTER + 1);
    let _ = c.submit_milestone(0, "e".into());
    approve_check(&mut c, AFTER + 2, "Approved", NEAR);
    pass_stage(&mut c, AFTER + 3);
    ctx(2, 0, AFTER + 2 + 600_001);
    let _ = c.finalize(0);
    let p = c.get_proposal(0).unwrap();
    assert!(p.pending);
    assert_eq!(p.outcome.unwrap().amount, U128(NEAR));
    assert_eq!(c.get_record(accounts(1)).delivered, 1);
}

#[test]
fn earlier_stages_stay_rebuildable() {
    let mut c = milestone_round();
    let stage0 = String::from_utf8(c.review_request(0, 1).into()).unwrap();
    pass_stage(&mut c, 3_000);
    ctx(2, 0, AFTER);
    let _ = c.finalize(0);
    dao_result(&mut c, AFTER, PromiseResult::Successful(b"17".to_vec()));
    ctx(1, NEAR, AFTER + 1);
    let _ = c.submit_milestone(0, "e".into());
    approve_check(&mut c, AFTER + 2, "Approved", NEAR);
    assert_eq!(String::from_utf8(c.stage_request(0, 0, 1).into()).unwrap(), stage0);
    assert!(String::from_utf8(c.stage_request(0, 1, 1).into()).unwrap().contains("stage 1"));
}

#[test]
fn review_event_names_its_stage() {
    let mut c = three_model_round();
    post(&mut c, 0, 0, 1, r#"{"score":4,"flags":[]}"#, 3_000);
    let log = near_sdk::test_utils::get_logs().into_iter().find(|l| l.starts_with("EVENT_JSON:")).unwrap();
    let v: near_sdk::serde_json::Value = near_sdk::serde_json::from_str(&log["EVENT_JSON:".len()..]).unwrap();
    assert_eq!(v["data"][0]["stage"], 0);
}
