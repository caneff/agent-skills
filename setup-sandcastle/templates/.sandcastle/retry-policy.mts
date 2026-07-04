import { readFileSync, writeFileSync } from "node:fs";

// Review-retry cap. A needs-review issue is re-reviewed (cheaply, on its
// existing branch) up to this many times before we give up on review-only and
// escalate to a full re-implement. A spec-fail issue is re-implemented up to
// this many times before being handed to a human. Without a cap, a
// deterministically-broken branch would re-review/re-fail every run forever.
export const REVIEW_RETRY_CAP = 2;

const ATTEMPTS_FILE = ".sandcastle/review-attempts.json";

// Per-key failed-attempt counters, persisted across runs. Keys are issue ids
// (review-retry) or `spec-<id>` (spec re-implement), kept distinct so the two
// caps count independently for the same issue.
export type Attempts = Record<string, number>;

export function readAttempts(file = ATTEMPTS_FILE): Attempts {
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch {
    return {};
  }
}

export function writeAttempts(a: Attempts, file = ATTEMPTS_FILE): void {
  writeFileSync(file, JSON.stringify(a, null, 2));
}

// Record one failed attempt against `key`. Returns the updated counters, the
// new count, and whether this attempt hit the cap (escalate). At the cap the
// counter is cleared so the next lifecycle (full re-implement / human handoff)
// starts fresh. Pure: the input map is not mutated.
export function recordAttempt(
  attempts: Attempts,
  key: string,
  cap = REVIEW_RETRY_CAP
): { attempts: Attempts; count: number; escalate: boolean } {
  const count = (attempts[key] ?? 0) + 1;
  const next = { ...attempts };
  if (count >= cap) {
    delete next[key];
    return { attempts: next, count, escalate: true };
  }
  next[key] = count;
  return { attempts: next, count, escalate: false };
}
