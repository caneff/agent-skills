// Address PR review comments — reusable from main.mts and as a CLI.
//
// For each PR it spins up a sandbox that checks out the PR branch, addresses
// the unresolved review comments, pushes the fixes back to the same branch
// (updating the open PR in place), and replies to each thread.
//
// Reply-only: it does NOT resolve threads and does NOT merge. You review the
// replies and resolve/merge yourself.
//
// Usage:
//   npx tsx .sandcastle/address.mts <pr-number> [<pr-number> ...]  # specific PRs
//   npx tsx .sandcastle/address.mts                                # sweep open sandcastle PRs with comments
// Or import { addressOpenPRs } and call it (main.mts does this at run start).

import { execSync } from "node:child_process";
import * as sandcastle from "@ai-hero/sandcastle";
import { sandboxIdentity, sandboxConfig } from "./sandbox-identity.mts";

const sh = (cmd: string) => execSync(cmd, { encoding: "utf8" }).trim();

// Address review comments on the given PRs. With no explicit numbers, sweep
// every open PR that (a) sits on a `sandcastle/*` branch — the runner's own
// work, never hand-authored PRs — and (b) actually has comments to address
// (skipped otherwise so we don't burn a sandbox finding nothing).
//
// Explicit PR numbers bypass the branch filter: you asked for those specifically.
export async function addressOpenPRs(prs?: string[]): Promise<void> {
  let list = prs ?? [];

  if (list.length === 0) {
    const slug = sh(`gh repo view --json nameWithOwner --jq .nameWithOwner`);
    const open = sh(
      `gh pr list --state open --json number,headRefName --jq '.[] | select(.headRefName | startswith("sandcastle/")) | .number'`
    )
      .split("\n")
      .filter(Boolean);
    list = open.filter((n) => {
      const inline = Number(
        sh(`gh api repos/${slug}/pulls/${n}/comments --jq 'length'`)
      );
      const top = Number(
        sh(`gh api repos/${slug}/issues/${n}/comments --jq 'length'`)
      );
      // Review summaries (a "Comment"/"Request changes" review with a body) live
      // in pulls/reviews, not the two comment endpoints above — count the ones
      // that carry text so a review-only PR isn't skipped as comment-free.
      const reviews = Number(
        sh(
          `gh api repos/${slug}/pulls/${n}/reviews --jq '[.[] | select(.body | length > 0)] | length'`
        )
      );
      return inline + top + reviews > 0;
    });
    if (list.length === 0) {
      console.log("No open sandcastle PRs with comments to address.");
      return;
    }
    console.log(`Open sandcastle PR(s) with comments: ${list.join(", ")}`);
  }

  // Mint once per run; installation tokens are valid ~1h, no caching needed.
  const identity = await sandboxIdentity();

  // Sequential: each run pushes to a branch, so we avoid concurrent pushes and
  // keep token spend predictable. `branchStrategy: branch` fetches that branch
  // into an isolated git worktree — it never touches your current checkout.
  for (const pr of list) {
    const branch = sh(`gh pr view ${pr} --json headRefName --jq .headRefName`);
    console.log(
      `\n=== Addressing review comments on PR #${pr} (${branch}) ===\n`
    );
    await sandcastle.run({
      ...sandboxConfig(identity),
      copyToWorktree: [".venv"],
      branchStrategy: { type: "branch", branch },
      name: `address-pr-${pr}`,
      maxIterations: 30,
      agent: sandcastle.claudeCode("claude-sonnet-5"),
      promptFile: "./.sandcastle/address-comments-prompt.md",
      promptArgs: { PR_NUMBER: pr },
    });
  }

  console.log("\nAll done.");
}

// CLI entry: run directly with `npx tsx .sandcastle/address.mts [pr ...]`.
if (import.meta.url === `file://${process.argv[1]}`) {
  await addressOpenPRs(process.argv.slice(2));
}
