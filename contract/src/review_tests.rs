use crate::tests::*;
use crate::*;
use ed25519_dalek::{Signer as _, SigningKey};
use near_sdk::test_utils::accounts;

pub(crate) const MODELS: [&str; 3] = ["model-a", "model-b", "model-c"];

pub(crate) fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

pub(crate) fn key(n: u8) -> SigningKey {
    SigningKey::from_bytes(&[n; 32])
}

fn response(content: &str) -> Vec<u8> {
    near_sdk::serde_json::json!({"id": "x", "choices": [{"message": {"role": "assistant", "content": content}}]})
        .to_string()
        .into_bytes()
}

fn sign(c: &Sieve, k: &SigningKey, model: &str, pid: u64, slot: u8, resp: &[u8]) -> String {
    let req: Vec<u8> = c.review_request(pid, slot).into();
    let text = format!("{model}:{}:{}", hex(&env::sha256(&req)), hex(&env::sha256(resp)));
    hex(&k.sign(text.as_bytes()).to_bytes())
}

/// Three-model round with keys 1, 2, 3 registered (expiring at 1,000,000,000 ms), no proposals yet.
pub(crate) fn three_model_round_without_proposal() -> Sieve {
    let mut c = setup_round(MODELS.iter().map(|m| m.to_string()).collect(), "rubric");
    ctx(0, 0, 1_500);
    for (i, m) in MODELS.iter().enumerate() {
        c.register_signer(hex(key(i as u8 + 1).verifying_key().as_bytes()), m.to_string(), 1_000_000_000);
    }
    c
}

/// Three-model round with keys registered and one proposal submitted at 2,000 ms by accounts(1).
pub(crate) fn three_model_round() -> Sieve {
    let mut c = three_model_round_without_proposal();
    ctx(1, NEAR, 2_000);
    c.submit(0, "title".into(), "body".into());
    c
}

pub(crate) fn post(c: &mut Sieve, pid: u64, slot: u8, signer: u8, content: &str, now_ms: u64) -> u8 {
    let resp = response(content);
    let sig = sign(c, &key(signer), MODELS[slot as usize], pid, slot, &resp);
    ctx(2, 0, now_ms);
    c.post_review(pid, slot, resp.into(), sig, hex(key(signer).verifying_key().as_bytes()))
}

#[test]
fn accepts_real_tee_signature() {
    let f = fixture();
    let model = f["model"].as_str().unwrap().to_string();
    let mut c = setup_round(vec![model.clone()], f["system"].as_str().unwrap());
    ctx(0, 0, 1_500);
    let pk = f["signature"]["signing_address"].as_str().unwrap().to_string();
    c.register_signer(pk.clone(), model, 10_000_000);
    ctx(1, NEAR, 2_000);
    let pid = c.submit(0, f["title"].as_str().unwrap().into(), f["body"].as_str().unwrap().into());
    c.set_seed_for_test(pid, f["seed"].as_u64().unwrap());
    ctx(2, 0, 3_000);
    let score = c.post_review(
        pid,
        0,
        b64(f["response_b64"].as_str().unwrap()).into(),
        f["signature"]["signature_hex"].as_str().unwrap().into(),
        pk,
    );
    assert_eq!(score as u64, f["score"].as_u64().unwrap());
    assert_eq!(c.get_proposal(pid).unwrap().slots[0].as_ref().unwrap().score, score);
}

#[test]
#[should_panic(expected = "bad signature")]
fn rejects_tampered_response() {
    let mut c = three_model_round();
    let resp = response(r#"{"score":3,"flags":[]}"#);
    let sig = sign(&c, &key(1), MODELS[0], 0, 0, &resp);
    let mut tampered = resp.clone();
    let i = tampered.iter().position(|&b| b == b'3').unwrap();
    tampered[i] = b'9';
    ctx(2, 0, 3_000);
    c.post_review(0, 0, tampered.into(), sig, hex(key(1).verifying_key().as_bytes()));
}

#[test]
#[should_panic(expected = "bad signature")]
fn rejects_signature_from_other_proposal() {
    let mut c = three_model_round();
    ctx(1, NEAR, 2_000);
    c.submit(0, "title".into(), "body".into());
    let resp = response(r#"{"score":9,"flags":[]}"#);
    let sig = sign(&c, &key(1), MODELS[0], 0, 0, &resp);
    ctx(2, 0, 3_000);
    c.post_review(1, 0, resp.into(), sig, hex(key(1).verifying_key().as_bytes()));
}

#[test]
#[should_panic(expected = "key is not registered for this model")]
fn rejects_wrong_model_key() {
    let mut c = three_model_round();
    post(&mut c, 0, 0, 2, r#"{"score":9,"flags":[]}"#, 3_000);
}

#[test]
#[should_panic(expected = "key is not registered for this model")]
fn rejects_unregistered_key() {
    let mut c = three_model_round();
    post(&mut c, 0, 0, 9, r#"{"score":9,"flags":[]}"#, 3_000);
}

#[test]
#[should_panic(expected = "signer key expired")]
fn rejects_expired_key() {
    let mut c = three_model_round();
    ctx(0, 0, 2_500);
    c.register_signer(hex(key(1).verifying_key().as_bytes()), MODELS[0].into(), 2_800);
    post(&mut c, 0, 0, 1, r#"{"score":5,"flags":[]}"#, 3_000);
}

#[test]
#[should_panic(expected = "review window closed")]
fn rejects_after_window() {
    let mut c = three_model_round();
    post(&mut c, 0, 0, 1, r#"{"score":5,"flags":[]}"#, 2_000 + 600_001);
}

#[test]
fn lower_score_replaces_higher() {
    let mut c = three_model_round();
    assert_eq!(post(&mut c, 0, 0, 1, r#"{"score":9,"flags":[]}"#, 3_000), 9);
    assert_eq!(post(&mut c, 0, 0, 1, r#"{"score":3,"flags":["low_effort"]}"#, 4_000), 3);
    assert_eq!(post(&mut c, 0, 0, 1, r#"{"score":5,"flags":[]}"#, 5_000), 3);
    let slot = c.get_proposal(0).unwrap().slots[0].clone().unwrap();
    assert_eq!((slot.score, slot.flags), (3, vec!["low_effort".to_string()]));
}

#[test]
fn parses_fenced_json() {
    let mut c = three_model_round();
    assert_eq!(post(&mut c, 0, 1, 2, "```json\n{\"score\": 4, \"flags\": []}\n```", 3_000), 4);
}

#[test]
#[should_panic(expected = "score must be an integer from 0 to 10")]
fn rejects_score_out_of_range() {
    let mut c = three_model_round();
    post(&mut c, 0, 0, 1, r#"{"score":11,"flags":[]}"#, 3_000);
}

#[test]
#[should_panic(expected = "score must be an integer from 0 to 10")]
fn rejects_score_as_string() {
    let mut c = three_model_round();
    post(&mut c, 0, 0, 1, r#"{"score":"9","flags":[]}"#, 3_000);
}

#[test]
#[should_panic(expected = "score must be an integer from 0 to 10")]
fn rejects_missing_score() {
    let mut c = three_model_round();
    post(&mut c, 0, 0, 1, r#"{"flags":[]}"#, 3_000);
}

#[test]
#[should_panic(expected = "not a review")]
fn rejects_prose() {
    let mut c = three_model_round();
    post(&mut c, 0, 0, 1, "Score: 9", 3_000);
}

#[test]
#[should_panic(expected = "response too large")]
fn rejects_oversize_response() {
    let mut c = three_model_round();
    let content = format!(r#"{{"score":1,"flags":[],"reason":"{}"}}"#, "x".repeat(64_000));
    post(&mut c, 0, 0, 1, &content, 3_000);
}

#[test]
fn review_emits_event_with_response() {
    let mut c = three_model_round();
    post(&mut c, 0, 2, 3, r#"{"score":6,"flags":[]}"#, 3_000);
    let logs = near_sdk::test_utils::get_logs();
    let log = logs.iter().find(|l| l.starts_with("EVENT_JSON:")).expect("event");
    let v: near_sdk::serde_json::Value = near_sdk::serde_json::from_str(&log["EVENT_JSON:".len()..]).unwrap();
    assert_eq!(v["event"], "review");
    let d = &v["data"][0];
    assert_eq!((d["proposal_id"].as_u64(), d["slot"].as_u64(), d["score"].as_u64()), (Some(0), Some(2), Some(6)));
    assert!(d.get("response").is_none(), "the answer stays in the transaction arguments, not the log");
    assert_eq!(d["response_hash"].as_str().unwrap(), hex(&env::sha256(&response(r#"{"score":6,"flags":[]}"#))));
    let _ = accounts(0);
}

#[test]
fn checklist_score_is_count_of_true_checks() {
    let mut c = three_model_round();
    let score = post(&mut c, 0, 0, 1, r#"{"checks":{"a":true,"b":false,"c":true,"d":true},"score":10,"flags":[]}"#, 3_000);
    assert_eq!(score, 3);
}

#[test]
#[should_panic(expected = "checks must be an object of at most 10 booleans")]
fn checklist_rejects_string_checks() {
    let mut c = three_model_round();
    post(&mut c, 0, 0, 1, r#"{"checks":{"a":"yes"},"flags":[]}"#, 3_000);
}

#[test]
#[should_panic(expected = "checks must be an object of at most 10 booleans")]
fn checklist_rejects_more_than_ten() {
    let mut c = three_model_round();
    let checks: Vec<String> = (0..11).map(|i| format!("\"c{i}\":true")).collect();
    post(&mut c, 0, 0, 1, &format!("{{\"checks\":{{{}}},\"flags\":[]}}", checks.join(",")), 3_000);
}

#[test]
fn accepts_long_reasoning_answer() {
    let mut c = three_model_round();
    let content = r#"{"score":5,"flags":[]}"#;
    let long = near_sdk::serde_json::json!({"id": "x", "choices": [{"message": {"role": "assistant", "content": content,
        "reasoning_content": "r".repeat(20_000)}}]}).to_string().into_bytes();
    let sig = sign(&c, &key(1), MODELS[0], 0, 0, &long);
    ctx(2, 0, 3_000);
    assert_eq!(c.post_review(0, 0, long.into(), sig, hex(key(1).verifying_key().as_bytes())), 5);
}
