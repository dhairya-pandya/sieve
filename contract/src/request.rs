//! The canonical review request. sieve/request.py builds the same bytes; change both or neither.

fn json_str(s: &str) -> String {
    near_sdk::serde_json::to_string(s).expect("string serializes")
}

use crate::Record;

pub fn user_message(round_id: u64, proposal_id: u64, title: &str, body: &str, record: &Record, stage: u8, evidence: Option<&str>) -> String {
    let mut text = format!(
        "Round {round_id}, proposal {proposal_id}, stage {stage}.\nApplicant record (written by the Sieve contract, not by the applicant): \
         first seen {} days before this submission; {} proposals submitted before this one; {} passed review; {} milestones delivered.\n\
         <proposal>\nTITLE: {title}\n\n{body}\n</proposal>",
        record.days, record.submitted, record.passed, record.delivered
    );
    if stage > 0 {
        text.push_str(&format!("\n<evidence milestone=\"{stage}\">\n{}\n</evidence>", evidence.unwrap_or("")));
    }
    text
}

#[allow(clippy::too_many_arguments)]
pub fn build(model: &str, system: &str, round_id: u64, proposal_id: u64, title: &str, body: &str, seed: u64,
             record: &Record, stage: u8, evidence: Option<&str>) -> Vec<u8> {
    format!(
        "{{\"model\":{},\"messages\":[{{\"role\":\"system\",\"content\":{}}},{{\"role\":\"user\",\"content\":{}}}],\"temperature\":0,\"seed\":{},\"response_format\":{{\"type\":\"json_object\"}}}}",
        json_str(model),
        json_str(system),
        json_str(&user_message(round_id, proposal_id, title, body, record, stage, evidence)),
        seed
    )
    .into_bytes()
}
