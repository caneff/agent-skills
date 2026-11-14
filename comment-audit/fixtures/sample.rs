/// Returns the byte length of `s` after trimming, or `None` when `s` is empty.
/// Callers rely on `None` meaning "no payload", never zero bytes.
pub fn payload_len(s: &str) -> Option<usize> {
    // (#399)
    let t = s.trim(); // trim s
    if t.is_empty() { None } else { Some(t.len()) }
}
