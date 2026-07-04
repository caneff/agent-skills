import type { OpenIssue, PrRef, PrState } from "./reconcile.mts";

// Pure parsers from raw `gh` CLI output into the orchestrator's domain types.
// The IO (running `gh`) stays in main.mts; everything fragile — JSON shape,
// missing fields, null/parse failure — is handled here so it can be tested
// against captured fixtures instead of only by live integration runs.

// Parse `gh issue list --json number,title,labels` output. Null/blank/parse
// failure → []; tolerant of an issue with no labels array.
export function parseOpenIssues(raw: string | null): OpenIssue[] {
  if (!raw) return [];
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(data)) return [];
  return (
    data as { number: number; title: string; labels?: { name: string }[] }[]
  ).map((i) => ({
    number: i.number,
    title: i.title,
    labels: (i.labels ?? []).map((l) => l.name),
  }));
}

// Parse the `closingIssuesReferences` GraphQL response into a map of
// issueNumber → the PRs that close it. GitHub populates closingIssuesReferences
// when a PR body carries a closing keyword such as "Closes #N".
// Null/parse failure/missing nodes → empty Map.
export function parsePrsClosingIssues(
  raw: string | null
): Map<number, PrRef[]> {
  const map = new Map<number, PrRef[]>();
  if (!raw) return map;
  let data: {
    data?: {
      repository?: {
        pullRequests?: {
          nodes?: {
            number: number;
            state: string;
            closingIssuesReferences?: { nodes?: { number: number }[] };
          }[];
        };
      };
    };
  };
  try {
    data = JSON.parse(raw);
  } catch {
    return map;
  }
  const prs = data?.data?.repository?.pullRequests?.nodes ?? [];
  for (const pr of prs) {
    for (const issue of pr.closingIssuesReferences?.nodes ?? []) {
      const n = issue.number;
      if (!map.has(n)) map.set(n, []);
      map.get(n)!.push({ number: pr.number, state: pr.state as PrState });
    }
  }
  return map;
}
