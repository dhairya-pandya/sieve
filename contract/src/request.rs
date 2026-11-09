//! The canonical review request. sieve/request.py builds the same bytes; change both or neither.

fn json_str(s: &str) -> String {
    near_sdk::serde_json::to_string(s).expect("string serializes")
}

pub fn user_message(round_id: u64, proposal_id: u64, title: &str, body: &str) -> String {
    format!("Round {round_id}, proposal {proposal_id}.\n<proposal>\nTITLE: {title}\n\n{body}\n</proposal>")
}

pub fn build(model: &str, system: &str, round_id: u64, proposal_id: u64, title: &str, body: &str, seed: u64) -> Vec<u8> {
    format!(
        "{{\"model\":{},\"messages\":[{{\"role\":\"system\",\"content\":{}}},{{\"role\":\"user\",\"content\":{}}}],\"temperature\":0,\"seed\":{},\"response_format\":{{\"type\":\"json_object\"}}}}",
        json_str(model),
        json_str(system),
        json_str(&user_message(round_id, proposal_id, title, body)),
        seed
    )
    .into_bytes()
}
