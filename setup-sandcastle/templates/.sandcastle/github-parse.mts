import { z } from "zod";
import type { OpenIssue } from "./reconcile.mts";

// Pure parsers from raw `gh` CLI output into the orchestrator's domain types.
// The IO (running `gh`) stays in main.mts; everything fragile — JSON shape,
// missing fields, null/parse failure — is handled here so it can be tested
// against captured fixtures instead of only by live integration runs.
//
// FAILURE POLICY — one rule, every parser in this file:
//
//   A parser never throws. Output that is absent, unparseable, or the wrong
//   shape yields exactly what the caller already gets when the `gh` call
//   itself failed: [], an empty Map, or null where the caller must tell "no
//   data" from "no rows".
//
// Degrade rather than throw because the orchestrator is a long unattended run.
// A malformed response to one of a dozen queries would otherwise abort a run
// that is mid-implementation on a real branch, and every caller here already
// has a considered answer for missing data. Degrading is not the same as going
// quiet: a shape that fails validation warns on stderr and lands in the run log.

// How many issues a query asks for. One convention applied at every call site.
//   OPEN_ISSUE_LIMIT covers every open-only query.
//   ALL_ISSUE_LIMIT covers `--state all`, which spans every issue the repo has
//   ever closed and so needs the higher ceiling.
// ponytail: a fixed limit, not paging. A backlog past these is a backlog
// problem; raise the numbers if a repo ever outgrows them.
export const OPEN_ISSUE_LIMIT = 200;
export const ALL_ISSUE_LIMIT = 1000;

// The one place the failure policy above is implemented. Returns null for
// every unusable input; each parser maps that null to its own empty value.
function decode<S extends z.ZodType>(
  schema: S,
  raw: string | null,
  what: string
): z.infer<S> | null {
  // A null/blank `raw` is the `gh` call having already failed — main.mts has
  // reported it, so re-warning here would double-log the same event.
  if (!raw) return null;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return warn(what, "response was not JSON");
  }
  const result = schema.safeParse(data);
  if (!result.success) {
    return warn(what, z.prettifyError(result.error).split("\n")[0] ?? "");
  }
  return result.data;
}

function warn(what: string, why: string): null {
  console.error(`  ! ${what}: ${why}; continuing without it`);
  return null;
}

const openIssuesSchema = z.array(
  z.object({
    number: z.number(),
    title: z.string(),
    labels: z.array(z.object({ name: z.string() })).optional(),
  })
);

// Parse `gh issue list --json number,title,labels` output.
export function parseOpenIssues(raw: string | null): OpenIssue[] {
  const rows = decode(openIssuesSchema, raw, "open issues") ?? [];
  return rows.map((i) => ({
    number: i.number,
    title: i.title,
    labels: (i.labels ?? []).map((l) => l.name),
  }));
}

const blockedByRowsSchema = z.array(
  z.object({ number: z.number(), blockedBy: z.array(z.number()) })
);

// Each issue's `blockedBy` edge ids, keyed by issue number — the raw edges the
// buildable-frontier filter (`selectBuildable`) reads to drop any issue with an
// open blocker.
export function parseBlockedByRows(raw: string | null): Map<number, number[]> {
  const map = new Map<number, number[]>();
  for (const row of decode(blockedByRowsSchema, raw, "blockedBy edges") ?? []) {
    map.set(row.number, row.blockedBy);
  }
  return map;
}

const issueEdgeRowsSchema = z.array(
  z.object({
    number: z.number(),
    state: z.enum(["OPEN", "CLOSED"]),
    parent: z.number().nullable(),
  })
);

export type IssueEdgeRow = z.infer<typeof issueEdgeRowsSchema>[number];

// Every issue's state and native parent, open AND closed — the one query
// behind the spent-parent check. Null when there is no usable answer; per the failure
// policy that is the same null a failed `gh` call produces, and each caller
// decides what it means. An empty array is a real answer (a repo with no
// issues) and stays distinct from it.
export function parseIssueEdges(raw: string | null): IssueEdgeRow[] | null {
  return decode(issueEdgeRowsSchema, raw, "issue edges");
}


