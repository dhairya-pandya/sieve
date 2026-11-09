//! Checking a signed review: the signed text, the key, and the score inside the model's answer.
//! The parsing rules match sieve/nearai.py::parse_review.
use near_sdk::serde_json::{self, Value};

pub const MAX_RESPONSE: usize = 9_000;

pub struct Parsed {
    pub score: u8,
    pub flags: Vec<String>,
}

pub fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

pub fn unhex<const N: usize>(s: &str) -> Option<[u8; N]> {
    if s.len() != N * 2 {
        return None;
    }
    let mut out = [0u8; N];
    for (i, chunk) in s.as_bytes().chunks(2).enumerate() {
        out[i] = u8::from_str_radix(std::str::from_utf8(chunk).ok()?, 16).ok()?;
    }
    Some(out)
}

fn strip_fence(content: &str) -> &str {
    let s = content.trim();
    if s.len() >= 6 && s.starts_with("```") && s.ends_with("```") {
        let inner = &s[3..s.len() - 3];
        if let Some(nl) = inner.find('\n') {
            let first = inner[..nl].trim();
            if !first.is_empty() && first.chars().all(char::is_alphabetic) {
                return inner[nl + 1..].trim();
            }
        }
        return inner.trim();
    }
    s
}

pub fn parse(response: &[u8]) -> Result<Parsed, &'static str> {
    let v: Value = serde_json::from_slice(response).map_err(|_| "not a review")?;
    let content = v["choices"][0]["message"]["content"].as_str().ok_or("not a review")?;
    let data: Value = serde_json::from_str(strip_fence(content)).map_err(|_| "not a review")?;
    let obj = data.as_object().ok_or("score must be an integer from 0 to 10")?;
    let score = match obj.get("checks") {
        // Checklist rubric: the score is the number of checks answered true, at most 10.
        Some(Value::Object(checks)) if checks.len() <= 10 && checks.values().all(Value::is_boolean) => {
            checks.values().filter(|v| v.as_bool() == Some(true)).count() as u64
        }
        Some(_) => return Err("checks must be an object of at most 10 booleans"),
        None => obj.get("score").and_then(Value::as_u64).filter(|s| *s <= 10).ok_or("score must be an integer from 0 to 10")?,
    };
    let flags = match obj.get("flags") {
        None => vec![],
        Some(Value::Array(items)) => items
            .iter()
            .map(|f| f.as_str().map(str::to_string))
            .collect::<Option<Vec<_>>>()
            .ok_or("flags must be a list of strings")?,
        Some(_) => return Err("flags must be a list of strings"),
    };
    Ok(Parsed { score: score as u8, flags })
}
