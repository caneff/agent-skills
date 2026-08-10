import { readFileSync, writeFileSync } from "node:fs";

import type { CheckStatus } from "./review-verdict.mts";

// Review-retry cap. A needs-review issue is re-reviewed (cheaply, on its
// existing branch) up to this many times before we give up on review-only and
// escalate to a full re-implement. A review-fail issue (spec and/or standards)
// is re-implemented up to this many times before being handed to a human.
// Without a cap, a deterministically-broken branch would re-review/re-fail
// every run forever.
export const REVIEW_RETRY_CAP = 2;

const ATTEMPTS_FILE = ".sandcastle/review-attempts.json";

// Per-key failed-attempt counters, persisted across runs. Keys are issue ids
// (review-retry) or `review-<id>` (re-implement after a failed review axis),
// kept distinct so the two caps count independently for the same issue.
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

// One gate verdict against a whole PR set: the Phase-3 full-suite gate judges
// every member at once, under one counter per member (#25). A `test-fail`
// counts one attempt against each key; a `pass` clears them, which is what makes
// the cap count CONSECUTIVE failures; a `harness-error` is an infra fault and is
// never counted, so a sandbox that failed to launch cannot retire a good set.
//
// `escalated` is an OR across every key, never last-one-wins. The set fails and
// passes in lockstep, so its counters normally move together — but recordAttempt
// deletes a key as it escalates, so counters that ever drifted apart would let a
// last-wins read miss the escalation and requeue the set forever. Pure: the
// input map is not mutated.
export function recordSetAttempt(
  attempts: Attempts,
  keys: string[],
  status: CheckStatus
): { attempts: Attempts; escalated: boolean } {
  let next = { ...attempts };
  if (status === "pass") {
    for (const key of keys) delete next[key];
    return { attempts: next, escalated: false };
  }
  if (status !== "test-fail") return { attempts: next, escalated: false };
  let escalated = false;
  for (const key of keys) {
    const r = recordAttempt(next, key);
    next = r.attempts;
    escalated ||= r.escalate;
  }
  return { attempts: next, escalated };
}
