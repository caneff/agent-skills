// Pure log-retention decision, split out of main.mts so it can be
// tested without touching the filesystem. Given a log file's lines and a cutoff
// (ms since epoch), decide what to keep. main.mts stays the thin file-IO caller.
//
// Sandcastle delimits each run with a `--- Run started: <ISO ts> ---` header.
// We keep from the first header newer than the cutoff onward:
//   keep-all   — that header is line 0; the whole file is recent, leave it.
//   keep-from  — it's further down; keep from that line (drop the stale prefix).
//   empty      — no recent run, OR the kept slice is only whitespace; drop it.
//                (A file with no header at all falls here too.)
export function planRetention(
  lines: string[],
  cutoffMs: number
):
  | { action: "keep-all" }
  | { action: "empty" }
  | { action: "keep-from"; index: number } {
  const hdr = /^--- Run started: (.+?) ---$/;
  let keepFrom = lines.length; // no recent run found → empty the file
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(hdr);
    if (m && Date.parse(m[1]) >= cutoffMs) {
      keepFrom = i;
      break;
    }
  }
  if (keepFrom === 0) return { action: "keep-all" };
  if (lines.slice(keepFrom).join("\n").trim() === "") return { action: "empty" };
  return { action: "keep-from", index: keepFrom };
}
