//! Turning slot scores into an outcome: the median, the pass rule, and what passing does.
use crate::Slot;

pub fn median(slots: &[Option<Slot>]) -> Option<(u8, usize)> {
    let mut scores: Vec<u8> = slots.iter().flatten().map(|s| s.score).collect();
    if scores.is_empty() {
        return None;
    }
    scores.sort_unstable();
    Some((scores[(scores.len() - 1) / 2], scores.len()))
}

pub fn flagged_injection(slots: &[Option<Slot>]) -> bool {
    slots.iter().flatten().any(|s| s.flags.iter().any(|f| f == "injection"))
}
